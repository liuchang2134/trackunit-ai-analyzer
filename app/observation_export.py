"""Export the same accepted, possibly sampled points used by the device chart."""
import csv
from datetime import datetime, timedelta
from hashlib import sha256
from io import StringIO
from typing import Literal

from app.device_overview import device_overview

Metric = Literal['operating_hours', 'idle_hours', 'fuel_remaining_percent']
Window = Literal['all', '6', '1']
UNITS = {'operating_hours': 'h', 'idle_hours': 'h', 'fuel_remaining_percent': '%'}


class ChangedObservations(ValueError):
    """The exported evidence would differ from the chart the user saw."""


def spreadsheet_text(value):
    text = '' if value is None else str(value)
    # Quoting handles delimiters, but spreadsheet software may still run formulas.
    if text.startswith(('\t', '\r', '\n')) or text.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + text
    return text


def export_observations(machine_id: str, dataset_id: str | None = None,
                        metric: Metric = 'operating_hours', window: Window = 'all',
                        expected_revision: str | None = None):
    if metric not in UNITS or window not in ('all', '6', '1'):
        raise ValueError('Unsupported metric or window')
    overview = device_overview(machine_id, dataset_id)
    if expected_revision is not None and expected_revision != overview['plot_revision']:
        raise ChangedObservations('Plotted observations changed')
    points = overview['series']
    if points and window != 'all':
        start = datetime.fromisoformat(points[-1]['recorded_at']) - timedelta(hours=int(window))
        points = [p for p in points if datetime.fromisoformat(p['recorded_at']) >= start]
    output = StringIO(newline='')
    writer = csv.writer(output, lineterminator='\r\n')
    writer.writerow(['machine_id', 'model', 'serial_number', 'dataset_id', 'source',
                     'plot_revision', 'window_hours', 'sampled_for_display',
                     'metric', 'unit', 'recorded_at', 'value'])
    identity = [spreadsheet_text(overview[key]) for key in
                ('machine_id', 'model', 'serial_number', 'dataset_id', 'source', 'plot_revision')]
    for point in points:
        writer.writerow([*identity, window, str(overview['sampled_for_display']).lower(),
                         metric, UNITS[metric], point['recorded_at'], point[metric]])
    name_id = sha256(machine_id.encode('utf-8')).hexdigest()[:8]
    filename = f'jilian-observations-{name_id}-{metric}-{window}.csv'
    return output.getvalue().encode('utf-8-sig'), filename
