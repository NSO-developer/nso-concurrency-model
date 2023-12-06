#!/usr/bin/env python3

"""A simple progress trace viewer example. See the NSO Observability
Exporter tools for more.
"""

import argparse
import csv
from datetime import datetime
import sys
from rich.live import Live
from rich.bar import Bar
from rich.console import Group
from rich.table import Table
from rich.text import Text
from rich.color import Color
from rich.style import Style
from rich.console import Console


def graph_progress_trace(file, oper):
    color_numbers = list(filter(lambda i: not i in [4, 16, 17, 18],
                                [i for i in range(1, 232)]))
    begin = 0.0
    size = 0.0
    bars = Group()
    spans = {}
    tids_color = {}

    table = Table(title=f'Progress Trace {file.name}')
    table.add_column("Trace ID", width=12, no_wrap=True)
    table.add_column("Event [Transaction ID]", min_width=40, max_width=60)
    table.add_column("Duration", min_width=8, no_wrap=True)
    span_duration = Text(" Span 0.0 ms")
    table.add_column(span_duration,
                     max_width=(int(Console().width)-12-60-8-15),
                     no_wrap=True)

    with Live(table) as live:
        event_num = ts_num = dur_num = tid_num = msg_num = span_num = \
        pspan_num = sess_num = trans_num = ds_num = srv_num = attr_num = False
        header = None
        for line in file:
            l = list(csv.reader([line]))[0]
            if l[0] == '':
                continue
            if header is None:
                i = 0
                for name in l:
                    if name == "EVENT TYPE":
                        event_num = i
                    elif name == "TIMESTAMP":
                        ts_num = i
                    elif name == "DURATION":
                        dur_num = i
                    elif name == "TRACE ID":
                        trace_num = i
                    elif name == "SPAN ID":
                        span_num = i
                    elif name == "PARENT SPAN ID":
                        pspan_num = i
                    elif name == "SESSION ID":
                        trans_num = i
                    elif name == "TRANSACTION ID":
                        sess_num = i
                    elif name == "DATASTORE":
                        ds_num = i
                    elif name == "MESSAGE":
                        msg_num = i
                    elif name == "SERVICE":
                        srv_num = i
                    elif name == "ATTRIBUTE VALUE":
                        attr_num = i
                    i += 1
                if l[event_num] == 'EVENT TYPE':
                    header = l
                continue
            if not oper and l[ds_num] == 'operational':
                continue
            event_type = l[event_num]
            ts = datetime.fromisoformat(l[ts_num]).timestamp()
            duration = float(l[dur_num]) if l[dur_num] else 0.0

            tid = l[trace_num][-12:] if trace_num else ''
            span = l[span_num] if span_num else ''
            pspan = l[pspan_num] if pspan_num else ''
            sid = l[sess_num] if sess_num else ''
            trans = l[trans_num] if trans_num else ''
            text = l[msg_num] if msg_num else ''
            srv = l[srv_num] if srv_num else ''
            attr = l[attr_num] if attr_num else ''
            key = f'{tid}{span}{pspan}{sid}{trans}{srv}{attr}{text}'

            if begin == 0.0:
                begin = ts
            size = ts - begin
            if event_type == 'start':
                if tid not in tids_color:
                    color = Color.from_ansi(color_numbers.pop(0))
                    tids_color[tid] = color
                else:
                    color=tids_color[tid]
                span = Bar(begin=size, end=size, size=size, color=color)
                d = Text('', style=Style(color=color))
                rtid = Text(tid, style=Style(color=color))
                rtext= Text(f'{text} {trans}', style=Style(color=color))
                spans[key] = span, d
                table.add_row(rtid, rtext, d, span)
            elif event_type == 'stop' and key in spans:
                s, d = spans[key]
                d.append(f'{duration*1000:0.3f}')
                s.end = size
            else:
                continue

        for s, _ in spans.values():
            s.size = size
        span_duration.plain = f'Span {size*1000:0.3f} ms'
        live.refresh()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = "A simple progress trace"
        " graph example. See the NSO Observability Exporter tools for more.")
    parser.add_argument('-o', action='store_true', default=False,
            help='include operational transactions')
    parser.add_argument('file', type=argparse.FileType('r', encoding='UTF-8'),
                        help='progress trace CSV file to process')
    args = parser.parse_args()
    graph_progress_trace(args.file, args.o)