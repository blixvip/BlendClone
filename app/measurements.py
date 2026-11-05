"""Reference observations and spatial metrics, separate from reconstruction claims."""
import cv2
import numpy as np


def silhouette_metrics(reference, rendered):
    a, b = np.asarray(reference, bool), np.asarray(rendered, bool)
    if a.shape != b.shape or a.ndim != 2:
        raise ValueError('Silhouette masks must have equal two-dimensional shape')
    union = np.logical_or(a, b).sum()
    iou = float(np.logical_and(a, b).sum() / union) if union else 1.0
    if not a.any() or not b.any():
        return dict(iou=iou, mean_distance=None, max_distance=None)
    kernel = np.ones((3, 3), np.uint8)
    edges = [m & ~cv2.erode(m.astype(np.uint8), kernel, borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool) for m in (a, b)]
    distances = [cv2.distanceTransform((~edge).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE) for edge in edges]
    errors = np.concatenate([distances[0][edges[1]], distances[1][edges[0]]])
    return dict(iou=iou, mean_distance=float(errors.mean()), max_distance=float(errors.max()))


def track_detections(frames, max_distance=50, max_gap=1):
    tracks = []
    for frame, detections in enumerate(frames):
        candidates = []
        for index, track in enumerate(tracks):
            last = track['samples'][-1]
            gap = frame - last['frame']
            if gap > max_gap + 1:
                continue
            x, y = last['x'], last['y']
            if len(track['samples']) > 1:
                before = track['samples'][-2]
                dt = last['frame'] - before['frame']
                x += (last['x'] - before['x']) * gap / dt
                y += (last['y'] - before['y']) * gap / dt
            for det, point in enumerate(detections):
                distance = float(np.hypot(point['x'] - x, point['y'] - y))
                if distance <= max_distance:
                    candidates.append((distance, index, det))
        used_tracks, used_detections = set(), set()
        for _, index, det in sorted(candidates):
            if index in used_tracks or det in used_detections:
                continue
            tracks[index]['samples'].append(dict(detections[det], frame=frame))
            used_tracks.add(index)
            used_detections.add(det)
        for det, point in enumerate(detections):
            if det not in used_detections:
                tracks.append(dict(id=len(tracks), samples=[dict(point, frame=frame)]))
    return tracks


def yellow_particles(image):
    """Splinter benchmark-specific observations; uncertain merged blobs stay documented."""
    b, g, r = cv2.split(image.astype(np.float32))
    mask = ((r > 140) & (g > 150) & (g > r * .8) & (g - b > 35)).astype(np.uint8)
    height, width = mask.shape
    roi = np.zeros_like(mask)
    roi[round(height * .39):round(height * .88), round(width * .24):round(width * .72)] = 1
    mask &= roi
    count, labels, stats, centers = cv2.connectedComponentsWithStats(mask)
    scale = height / 1920
    found = []
    for index in range(1, count):
        x, y, w, h, area = stats[index]
        if 45 * scale * scale <= area <= 5000 * scale * scale and w < 100 * scale and h < 120 * scale:
            component = labels[y:y+h, x:x+w] == index
            color = np.median(image[y:y+h, x:x+w][component], axis=0).astype(int)
            found.append(dict(x=float(centers[index][0]), y=float(centers[index][1]),
                              rx=float(w / 2), ry=float(h / 2), color='#{:02x}{:02x}{:02x}'.format(*color[::-1])))
    return found
