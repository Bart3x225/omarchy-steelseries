"""Real battery telemetry history; no polling, synthetic samples or hardware IO."""
import os
from pathlib import Path
import sqlite3
import time

RETENTION_SECONDS = 30 * 86400
SAMPLE_SECONDS = 300
MAX_GAP_SECONDS = 900
MAX_POINTS = 200


def _estimate(rows):
    """Approximate remaining minutes, based only on a monotone discharge segment."""
    if len(rows) < 3 or rows[-1][0] - rows[0][0] < 1800 or rows[0][1] - rows[-1][1] < 5:
        return -1, 0
    if any(row[2] for row in rows) or any(
            right[1] > left[1] or not 0 < right[0] - left[0] <= MAX_GAP_SECONDS
            for left, right in zip(rows, rows[1:])):
        return -1, 0
    # Least-squares slope. Center relative timestamps to avoid epoch precision loss.
    xs = [row[0] - rows[0][0] for row in rows]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(row[1] for row in rows) / len(rows)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    slope = sum((x - mean_x) * (row[1] - mean_y) for x, row in zip(xs, rows)) / denominator
    if slope >= 0:
        return -1, 0
    return max(0, round(rows[-1][1] / -slope / 60)), len(rows)


def record_and_summarize(devices, now=None, db_path=None):
    """Return current-device summaries; time is epoch seconds and can be injected.

    estimateMinutes is approximate; -1/zero samples means insufficient evidence.
    SQLite errors propagate so the caller can surface a persistence error honestly.
    """
    now = int(time.time() if now is None else now)
    path = Path(db_path) if db_path is not None else Path(
        os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') / 'omarchy/steelseries/history.sqlite3'
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    try:
        connection.execute('CREATE TABLE IF NOT EXISTS samples (device TEXT, ts INTEGER, battery INTEGER, charging INTEGER, segment INTEGER)')
        connection.execute('CREATE INDEX IF NOT EXISTS samples_device_time ON samples(device,ts)')
        connection.execute('CREATE INDEX IF NOT EXISTS samples_time ON samples(ts)')
        connection.execute('CREATE TABLE IF NOT EXISTS status (device TEXT PRIMARY KEY, ts INTEGER, battery INTEGER, charging INTEGER, segment INTEGER, active INTEGER)')
        result = {}
        devices = {d['id']: d for d in devices if isinstance(d, dict) and isinstance(d.get('id'), str) and d['id']}
        with connection:
            cutoff = now - RETENTION_SECONDS
            if connection.execute('SELECT 1 FROM samples WHERE ts < ? LIMIT 1', (cutoff,)).fetchone():
                connection.execute('DELETE FROM samples WHERE ts < ?', (cutoff,))
            if connection.execute('SELECT 1 FROM status WHERE ts < ? LIMIT 1', (cutoff,)).fetchone():
                connection.execute('DELETE FROM status WHERE ts < ?', (cutoff,))
            statuses = {row[0]: row[1:] for row in connection.execute('SELECT * FROM status')}
            for ident, last in statuses.items():
                if ident not in devices and last[4]:
                    connection.execute('UPDATE status SET active=0 WHERE device=?', (ident,))
            for ident, device in devices.items():
                battery = device.get('battery')
                charging = device.get('charging')
                valid = (device.get('state') == 'connected' and not device.get('error')
                         and device.get('battery_supported', True) is not False
                         and type(battery) is int and 0 <= battery <= 100
                         and type(charging) is bool)
                last = statuses.get(ident)
                segment = last[3] if last else 0
                if not valid:
                    if last and last[4]:
                        connection.execute('UPDATE status SET active=0 WHERE device=?', (ident,))
                elif last is None or (now > last[0] and (not last[4] or now - last[0] >= SAMPLE_SECONDS
                        or battery != last[1] or charging != bool(last[2]))):
                    if last and (not last[4] or charging or last[2] or battery > last[1]
                                 or now - last[0] > MAX_GAP_SECONDS):
                        segment += 1
                    connection.execute('INSERT INTO samples VALUES (?,?,?,?,?)', (ident, now, battery, int(charging), segment))
                    connection.execute('INSERT OR REPLACE INTO status VALUES (?,?,?,?,?,1)',
                                       (ident, now, battery, int(charging), segment))
                    last = (now, battery, int(charging), segment, 1)
                rows = connection.execute('SELECT ts,battery,charging,segment FROM samples WHERE device=? ORDER BY ts', (ident,)).fetchall()
                estimate, samples = -1, 0
                if valid and not charging and last and last[4] and 0 <= now - last[0] <= MAX_GAP_SECONDS:
                    estimate, samples = _estimate([row for row in rows if row[3] == segment])
                if len(rows) > MAX_POINTS:
                    rows = [rows[index * (len(rows) - 1) // (MAX_POINTS - 1)] for index in range(MAX_POINTS)]
                points = [{'ts': row[0], 'battery': row[1], 'charging': bool(row[2])} for row in rows]
                result[ident] = dict(points=points, estimateMinutes=estimate, estimateSamples=samples)
        return result
    finally:
        connection.close()
