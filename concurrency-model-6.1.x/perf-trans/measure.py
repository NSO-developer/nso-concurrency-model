"""NSO transaction performance example.

Demo script
Permission to use this code as a starting point hereby granted

See the README file for more information
"""

import argparse
import csv
from datetime import datetime
from functools import partial
import json
from multiprocessing import Pool
from multiprocessing import Manager
import os
import secrets
import time
import requests
from requests.exceptions import ConnectionError

# Text color codes
HEADER = '\033[95m'
OKBLUE = '\033[94m'
OKCYAN = '\033[96m'
OKGREEN = '\033[92m'
ENDC = '\033[0m'
BOLD = '\033[1m'
UNDERLINE = '\033[4m'

# RESTCONF setup
AUTH = ('admin', 'admin')
BASE_URL = 'http://localhost:8080/restconf'
session = requests.Session()
session.auth = AUTH
headers = {'Content-Type': 'application/yang-data+json'}
headers_patch = {'Content-Type': 'application/yang-patch+json'}
headers_stream = {'Content-Type': 'text/event-stream'}

# The metrics from the NSO progress trace of interest
TRACE_METRICS = [
    'restconf edit',
    'applying transaction',
    'waiting to apply',
    'creating rollback checkpoint',
    'creating rollback file',
    'creating pre-transform checkpoint',
    'run pre-transform validation',
    'creating transform checkpoint',
    'run transforms and transaction hooks',
    'taking service write lock',
    'holding service write lock',
    'run service',
    'evaluate delayed when expressions',
    'creating validation checkpoint',
    'mark inactive',
    'pre validate',
    'run validation over the changeset',
    'run dependency-triggered validation',
    'check configuration policies',
    'check for read-write conflicts',
    'taking transaction lock',
    'holding transaction lock',
    'applying service meta-data',
    'write-start',
    'match subscribers',
    'create pre commit running',
    'write changeset',
    'check data kickers',
    'prepare',
    'push configuration',
    'commit',
    'switch to new running'
]


def find_transaction_times(fname):
    """Get the transaction times for the metrics of interest"""
    result = {}
    with open(fname, 'r', encoding='utf-8') as f:
        csvfile = csv.reader(f)
        i = j = 0
        tis_num = tid_num = msg_num = evt_num = -1
        for item in csvfile:
            # Get the column number for the duration, trace id and message as
            # they can differ between NSO versions.
            if i == 0:
                for name in item:
                    if name == "DURATION":
                        tis_num = j
                    elif name == "TRACE ID":
                        tid_num = j
                    elif name == "MESSAGE":
                        msg_num = j
                    elif name == "EVENT TYPE":
                        evt_num = j
                    j += 1
                    if tis_num != -1 and tid_num != -1 and msg_num != -1 and\
                       evt_num != -1:
                        break
            metric = item[msg_num]
            # The "stop" event type has the duration value we need
            if item[evt_num] == 'stop' and metric in TRACE_METRICS:
                # We use the trace id to identify the transaction
                trace_id = item[tid_num]
                if trace_id not in result:
                    result[trace_id] = {}
                result[trace_id][metric] = float(item[tis_num])
            i += 1

    return result


def average_transaction_times(data):
    """Calculate the averages"""
    n = len(data)
    if n < 1:
        n = 1

    sums = {}
    for metric in TRACE_METRICS:
        sums[metric] = 0

    for tx in data.values():
        for metric in TRACE_METRICS:
            # Check that the metric exists in the data from the CSV file
            if metric in tx:
                sums[metric] += tx[metric]

    for metric in TRACE_METRICS:
        sums[metric] = sums[metric] / n

    return sums


def setup_tracing():
    """Get a unique run ID to name the CSV file used by the NSO progress trace.
    Tip: Can be imported to your favourite spreadsheet application to get a
    detailed overview of the NSO transaction steps and timings after the test
    has finished.
    """
    run_id = secrets.token_urlsafe(4)
    fname = f't3-{run_id}.csv'
    fpath = f'logs/{fname}'

    # Enable the NSO progress trace
    D_DATA = {}
    D_DATA["name"] = "t3-trace"
    D_DATA["destination"] = {"file": fname, "format": "csv"}
    D_DATA["enabled"] = True
    #D_DATA["filter"] = {"context": "rest"}
    T_DATA = {}
    T_DATA["trace"] = [D_DATA]
    INPUT_DATA = {"tailf-progress:progress": T_DATA}

    PATH = '/data?unhide=debug'
    print(f"{BOLD}PATCH " + BASE_URL + PATH + f"{ENDC}")
    print(f"{HEADER}" + json.dumps(INPUT_DATA, indent=2) + f"{ENDC}")
    r = session.patch(BASE_URL + PATH, json=INPUT_DATA, headers=headers)
    print(r.text)
    print(f"Status code: {r.status_code}\n")

    return run_id, fpath


def disable_tracing():
    """Disable the NSO progress trace"""
    D_DATA = {}
    D_DATA["name"] = "t3-trace"
    D_DATA["enabled"] = False
    T_DATA = {}
    T_DATA["trace"] = [D_DATA]
    INPUT_DATA = {"tailf-progress:progress": T_DATA}

    PATH = '/data?unhide=debug'
    print(f"{BOLD}PATCH " + BASE_URL + PATH + f"{ENDC}")
    print(f"{HEADER}" + json.dumps(INPUT_DATA, indent=2) + f"{ENDC}")
    r = session.patch(BASE_URL + PATH, json=INPUT_DATA, headers=headers)
    print(r.text)
    print(f"Status code: {r.status_code}\n")


def test(cqparam, result_q, run_id, i):
    """Configure a service in a transaction using RESTCONF.
    Store the result in a Python multiprocessing queue.
    """
    lsession = requests.Session()
    lsession.auth = AUTH
    try:
        T3_DATA = {}
        T3_DATA["id"] = f"{i}"
        T3_DATA["value"] = f"{i}-{run_id}"
        T3S_DATA = {"t3": [T3_DATA]}
        INPUT_DATA = {"t3:t3s": [T3S_DATA]}

        PATH = f'/data{cqparam}'
        print(f"{BOLD}PATCH " + BASE_URL + PATH + f"{ENDC} id: {i}"
              f" value: {i}-{run_id}")
        #print(f"{HEADER}" + json.dumps(INPUT_DATA, indent=2) + f"{ENDC}")
        r = None
        trycnt = 5  # max try count
        while trycnt > 0:
            try:
                r = lsession.patch(BASE_URL + PATH, json=INPUT_DATA,
                                   headers=headers)
                trycnt = 0 # success
            except ConnectionError as e:
                if trycnt <= 0:
                    result_q.put(e)  # done retrying
                else:
                    print(f'Retry id: {i} value: {i}-{run_id}'
                          f' trycnt: {trycnt} exception: {e}')
                    trycnt -= 1  # retry
                    time.sleep(i/50)  # wait then retry
        print(r.text)
        print(f"Status code: {r.status_code}\n")

        if r.status_code >= 200 and r.status_code < 300:
            result_q.put(True)
        else:
            result_q.put(r.status_code)
    except Exception as e:
        result_q.put(e)


def run_test(nacq, cqparam, ntrans, ndtrans):
    """Run the test and print the results"""
    # Initialize the NSO progress trace
    run_id, csv_file = setup_tracing()

    # Use a managed Python pool to send multiple RESTCONF requests in parallel.
    m = Manager()
    result_q = m.Queue()
    dt_string = datetime.utcnow().isoformat() # For receiving only new
                                              # notifications
    start = time.time() # For measuring wall-clock time
    with Pool(ntrans) as p:
        p.map(partial(test, cqparam, result_q, run_id), range(ntrans))
        p.close()
        p.join()

    # Get the result from the processes
    ok_requests = 0
    while result_q.qsize():
        result = result_q.get()
        if result is True:
            ok_requests += 1
        else:
            print(f"{HEADER}A RESTCONF request failed! {ENDC}", result,
                  result_q.qsize())

    # All RESTCONF requests sent.
    ok_acq = 0
    if nacq > 0:
        # Now waiting for the service commit queue
        # event notifications if we are using asynchronous commit to queues to
        # send the requests from processes as fast as possible when we have more
        # requests in-progress than CPU cores.
        n_cqtrans = 0
        PATH = '/streams/service-state-changes/json?start-time=' + dt_string
        print(f"{BOLD}GET " + BASE_URL + PATH + f"{ENDC}")
        with session.get(BASE_URL + PATH, headers=headers_stream,
                        stream=True) as r:
            for notifs_str in r.iter_content(chunk_size=None,
                                            decode_unicode=True):
                notifs_str = notifs_str.replace('data: ', '')
                notifs = notifs_str.split("\n\n")
                for notif_str in notifs:
                    if len(notif_str) and "tailf-ncs:service-commit-queue" \
                       + "-event" in notif_str:
                        notif = json.loads(notif_str)
                        status = notif["ietf-restconf:notification"] \
                                    ["tailf-ncs:service-commit-queue-event"] \
                                    ["status"]
                        if status == "completed":
                            ok_acq += 1
                            n_cqtrans += 1
                            print("Commit queue item completed")
                            #print(notif_str)
                        elif status == "failed":
                            n_cqtrans += 1
                            print(f"{HEADER}A transaction in a commit queue"
                                f" failed! {ENDC}", notif_str)
                if n_cqtrans == nacq or n_cqtrans == ok_requests:
                    break

    total = time.time() - start  # Total wall-clock time for the test

    # Disable the NSO progress trace
    disable_tracing()

    # Parse the CSV file to get the metrics of interest
    nfound = 0
    while True:
        data = find_transaction_times(csv_file)
        for tx in data.values():
            # Check that the values for all transactions have been written to
            # the CSV file
            if TRACE_METRICS[0] in tx:
                nfound += 1
                if nfound == ntrans:
                    break
        if nfound == ntrans:
            break

        # Wait for the metrics to be written to the CSV file
        nfound = 0
        time.sleep(0.1)

    # Get the average transaction times for the metrics
    avgs = average_transaction_times(data)
    duration = avgs['restconf edit']

    # Present the progress trace details for averages per transaction
    print(f'\n{UNDERLINE}Detailed averages for N={ntrans} transactions:{ENDC}')
    restconf_edit = duration
    print(f'{OKCYAN}restconf edit{ENDC}')
    applying_transaction = avgs['applying transaction']
    print(f'{OKCYAN}applying transaction{ENDC}')
    waiting_to_apply = avgs['waiting to apply']
    print(f'{OKBLUE}waiting to apply:{ENDC}                                 '
          '{:5.2f}% {:.4f}s'.format(waiting_to_apply/duration*100,
                                    waiting_to_apply))
    creating_rollback_checkpoint = avgs['creating rollback checkpoint']
    print(f'{OKBLUE}creating rollback checkpoint:{ENDC}                     '
          '{:5.2f}% {:.4f}s'.format(creating_rollback_checkpoint/duration*100,
                                    creating_rollback_checkpoint))
    creating_rollback_file = avgs['creating rollback file']
    print(f'{OKBLUE}creating rollback file:{ENDC}                           '
          '{:5.2f}% {:.4f}s'.format(creating_rollback_file/duration*100,
                                    creating_rollback_file))
    creating_pre_transform_checkpoint = avgs['creating pre-transform'
                                             ' checkpoint']
    print(f'{OKBLUE}creating pre-transform checkpoint:{ENDC}                '
          '{:5.2f}% {:.4f}s'.format(
                                creating_pre_transform_checkpoint/duration*100,
                                creating_pre_transform_checkpoint))
    run_pre_transform_validation = avgs['run pre-transform validation']
    print(f'{OKBLUE}run pre-transform validation:{ENDC}                     '
          '{:5.2f}% {:.4f}s'.format(run_pre_transform_validation/duration*100,
                                    run_pre_transform_validation))
    creating_transform_checkpoint = avgs['creating transform checkpoint']
    print(f'{OKBLUE}creating transform checkpoint:{ENDC}                    '
          '{:5.2f}% {:.4f}s'.format(creating_transform_checkpoint/duration*100,
                                    creating_transform_checkpoint))
    run_transforms_and_transaction_hooks = avgs['run transforms and transaction'
                                                ' hooks']
    print(f'{OKCYAN}run transforms and transaction hooks{ENDC}')
    taking_service_write_lock = avgs['taking service write lock']
    print(f'{OKBLUE}taking service write lock:{ENDC}                        '
          '{:5.2f}% {:.4f}s'.format(taking_service_write_lock/duration*100,
                                    taking_service_write_lock))
    holding_service_write_lock = avgs['holding service write lock']
    print(f'{OKCYAN}holding service write lock{ENDC}')
    run_service = avgs['run service']
    print(f'{OKBLUE}run service:{ENDC}                                      '
          '{:5.2f}% {:.4f}s'.format(run_service/duration*100,
                                    run_service))
    evaluate_delayed_when_expressions = avgs['evaluate delayed when'
                                             ' expressions']
    print(f'{OKBLUE}evaluate delayed when expressions:{ENDC}                '
          '{:5.2f}% {:.4f}s'.format(
                                evaluate_delayed_when_expressions/duration*100,
                                evaluate_delayed_when_expressions))
    print(f'{OKCYAN}done run transforms and transaction hooks:{ENDC}        '
          '{:5.2f}% {:.4f}s'.format(
                             run_transforms_and_transaction_hooks/duration*100,
                             run_transforms_and_transaction_hooks))
    creating_validation_checkpoint = avgs['creating validation checkpoint']
    print(f'{OKBLUE}creating validation checkpoint:{ENDC}                   '
          '{:5.2f}% {:.4f}s'.format(creating_validation_checkpoint/duration*100,
                                    creating_validation_checkpoint))
    mark_inactive = avgs['mark inactive']
    print(f'{OKBLUE}mark inactive:{ENDC}                                    '
          '{:5.2f}% {:.4f}s'.format(mark_inactive/duration*100,
                                    mark_inactive))
    pre_validate = avgs['pre validate']
    print(f'{OKBLUE}pre validate:{ENDC}                                     '
          '{:5.2f}% {:.4f}s'.format(pre_validate/duration*100,
                                    pre_validate))
    run_validation_over_the_changeset = avgs['run validation over the'
                                             ' changeset']
    print(f'{OKBLUE}run validation over the changeset:{ENDC}                '
          '{:5.2f}% {:.4f}s'.format(
                                run_validation_over_the_changeset/duration*100,
                                run_validation_over_the_changeset))
    run_dependency_triggered_validation = avgs['run dependency-triggered'
                                               ' validation']
    print(f'{OKBLUE}run dependency-triggered validation:{ENDC}              '
          '{:5.2f}% {:.4f}s'.format(
                              run_dependency_triggered_validation/duration*100,
                              run_dependency_triggered_validation))
    check_configuration_policies = avgs['check configuration policies']
    print(f'{OKBLUE}check configuration policies:{ENDC}                     '
          '{:5.2f}% {:.4f}s'.format(check_configuration_policies/duration*100,
                                    check_configuration_policies))
    check_for_read_write_conflicts = avgs['check for read-write conflicts']
    print(f'{OKBLUE}check for read-write conflicts:{ENDC}                   '
          '{:5.2f}% {:.4f}s'.format(check_for_read_write_conflicts/duration*100,
                                    check_for_read_write_conflicts))
    taking_transaction_lock = avgs['taking transaction lock']
    print(f'{OKBLUE}taking transaction lock:{ENDC}                          '
          '{:5.2f}% {:.4f}s'.format(taking_transaction_lock/duration*100,
                                    taking_transaction_lock))
    holding_transaction_lock = avgs['holding transaction lock']
    print(f'{OKCYAN}holding transaction lock{ENDC}')
    applying_service_meta_data = avgs['applying service meta-data']
    print(f'{OKBLUE}applying service meta-data:{ENDC}                       '
          '{:5.2f}% {:.4f}s'.format(applying_service_meta_data/duration*100,
                                    applying_service_meta_data))
    write_start = avgs['write-start']
    print(f'{OKCYAN}write-start:{ENDC}')
    match_subscribers = avgs['match subscribers']
    print(f'{OKBLUE}match subscribers:{ENDC}                                '
          '{:5.2f}% {:.4f}s'.format(match_subscribers/duration*100,
                                    match_subscribers))
    create_pre_commit_running = avgs['create pre commit running']
    print(f'{OKBLUE}create pre commit running:{ENDC}                        '
          '{:5.2f}% {:.4f}s'.format(create_pre_commit_running/duration*100,
                                    create_pre_commit_running))
    write_changeset = avgs['write changeset']
    print(f'{OKBLUE}write changeset:{ENDC}                                  '
          '{:5.2f}% {:.4f}s'.format(write_changeset/duration*100,
                                    write_changeset))
    check_data_kickers = avgs['check data kickers']
    print(f'{OKBLUE}check data kickers:{ENDC}                               '
          '{:5.2f}% {:.4f}s'.format(check_data_kickers/duration*100,
                                    check_data_kickers))
    print(f'{OKCYAN}done write-start:{ENDC}                                 '
          '{:5.2f}% {:.4f}s'.format(write_start/duration*100,
                                    write_start))
    prepare = avgs['prepare']
    print(f'{OKCYAN}prepare{ENDC}')
    push_configuration = avgs['push configuration']
    print(f'{OKBLUE}push configuration:{ENDC}                               '
          '{:5.2f}% {:.4f}s'.format(push_configuration/duration*100,
                                    push_configuration))
    print(f'{OKCYAN}done prepare:{ENDC}                                     '
          '{:5.2f}% {:.4f}s'.format(prepare/duration*100,
                                    prepare))
    commit = avgs['commit']
    print(f'{OKCYAN}commit{ENDC}')
    switch_to_new_running = avgs['switch to new running']
    print(f'{OKBLUE}switch to new running:{ENDC}                            '
          '{:5.2f}% {:.4f}s'.format(switch_to_new_running/duration*100,
                                    switch_to_new_running))
    print(f'{OKCYAN}done holding service write lock:{ENDC}                  '
          '{:5.2f}% {:.4f}s'.format(holding_service_write_lock/duration*100,
                                    holding_service_write_lock))
    print(f'{OKCYAN}done holding transaction lock:{ENDC}                    '
          '{:5.2f}% {:.4f}s'.format(holding_transaction_lock/duration*100,
                                    holding_transaction_lock))
    print(f'{OKCYAN}done commit:{ENDC}                                      '
          '{:5.2f}% {:.4f}s'.format(commit/duration*100,
                                    commit))
    print(f'{OKCYAN}done applying transaction:{ENDC}                        '
          '{:5.2f}% {:.4f}s'.format(applying_transaction/duration*100,
                                    applying_transaction))
    print(f'{OKCYAN}done restconf edit:{ENDC}                               '
          '{:5.2f}% {:.4f}s'.format(restconf_edit/duration*100,
                                    restconf_edit))

    # Present an overview for averages per transaction
    service_time = (avgs['run service'] +
                avgs['evaluate delayed when expressions'])
    validation = (avgs['run validation over the changeset']
                  + avgs['run dependency-triggered validation'])
    queued_trans_lock = avgs['taking transaction lock']
    trans_lock = avgs['holding transaction lock']
    devices = (avgs['prepare'] + avgs['commit'])
    queued_service_lock = avgs['taking service write lock']
    print(f'\n{UNDERLINE}Averages for N={ntrans} transactions:{ENDC}')
    print(f'{OKBLUE}Start-to-finish time:{ENDC}                             '
          f'{duration:5.2f}s')
    print(f'{OKBLUE}Queued waiting for an available core:{ENDC}             '
          '{:5.2f}% {:.2f}s'.format(waiting_to_apply/duration*100,
                                    waiting_to_apply))
    print(f'{OKBLUE}Queued taking the service lock (old trans. lock):{ENDC} '
          '{:5.2f}% {:.2f}s'.format(queued_service_lock/duration*100,
                                    queued_service_lock))
    print(f'{OKBLUE}Running services - including code:{ENDC}                '
          '{:5.2f}% {:.2f}s'.format(service_time/duration*100, service_time))
    print(f'{OKBLUE}Validation - including code:{ENDC}                      '
          '{:5.2f}% {:.2f}s'.format(validation/duration*100, validation))
    print(f'{OKBLUE}Queued taking the transaction lock:{ENDC}               '
          '{:5.2f}% {:.2f}s'.format(queued_trans_lock/duration*100,
                                    queued_trans_lock))
    print(f'{OKBLUE}Holding transaction lock:{ENDC}                     '
        '    {:5.2f}% {:.2f}s'.format(trans_lock/duration*100, trans_lock))
    if ndtrans > 0:
        print(f'{OKBLUE}...of which updating devices:{ENDC}             '
            '        '
            '{:5.2f}% {:.2f}s'.format(devices/trans_lock*100, devices))
    if push_configuration > trans_lock: # Using sync commit queues
        print(f'{OKBLUE}Pushing the configuration:{ENDC}                    '
            '    {:5.2f}% {:.2f}s'.format(push_configuration/duration*100,
                                          push_configuration))

    # Present the results
    print(f'\n{UNDERLINE}Results for N={ntrans} transactions:{ENDC}')
    print(f'{OKBLUE}Number of CPU cores:    {ENDC}',
          os.cpu_count())
    print(f'{OKBLUE}Number of transactions: {ENDC}', ntrans)

    if ok_requests == ntrans:
        print(f'{OKGREEN}Successful requests:{ENDC}     '
              f'100%')
    elif ok_requests < 1:
        print(f'{HEADER}Successful requests:{ENDC}     '
              f'  0%')
    else:
        print(f'{BOLD}Successful requests:{ENDC}     '
              f'{ok_requests/ntrans:.0%}')

    print(f'{OKBLUE}Wall-clock time:{ENDC}         '
        f'{total:.2f}s\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('-nw', '--nwork', type=int, default="3",
                        help='Work per transaction in the service create and' +
                             ' validation phases. One second of CPU time' +
                             ' per work item. Default: 3')
    parser.add_argument('-nt', '--ntrans', type=int,
                        default=f"{os.cpu_count()}",
                        help='Number of transactions updating the same' +
                             ' service in parallel. Default: Number of CPU' +
                             ' cores')
    # Get the number of devices confgured with NSO to use as the upper limit
    PATH = "/data?fields=tailf-ncs:devices/device(name)"
    print(f"{BOLD}GET " + BASE_URL + PATH + f"{ENDC}")
    r = session.get(BASE_URL + PATH, headers=headers)
    ndevs = len(r.json()["ietf-restconf:data"]["tailf-ncs:devices"]["device"])
    parser.add_argument('-nd', '--ndtrans', choices=range(0, ndevs+1), type=int,
                        default=1,
                        help='Number of devices the service will configure'
                             ' per service transaction. Default: 1')
    parser.add_argument('-dd', '--ddelay', type=int, default=0,
                        help='Transaction delay on the devices (seconds).'
                             ' Default: 0s')
    parser.add_argument('-cq', '--cqparam', choices=['async', 'sync',
                                                    'bypass', 'none'],
                        default='none', help='Commit queue behavior. Select'
                        ' "none" to use global or device setting.'
                        ' setting. Default: none')
    args = parser.parse_args()

    cqparam = f'?commit-queue={args.cqparam}'
    if 'none' in cqparam:
        cqparam = ''

    # Get the number of devices with async commit queue enabled.
    # We will receive a "completed" notification when the config has been
    # pushed to those devices.
    nacq = 0
    if 'async' in cqparam:
        nacq = args.ntrans * args.ndtrans
        print("All devices have async commit queues enabled")
    elif cqparam == '':
        PATH = '/data/tailf-ncs:devices/global-settings/commit-queue'
        print(f"{BOLD}GET " + BASE_URL + PATH + f"{ENDC}")
        r = session.get(BASE_URL + PATH, headers=headers)
        if 'enabled-by-default": true' in r.text and '"sync"' not in r.text:
            nacq = args.ntrans * args.ndtrans
            print("All devices have async cqs enabled")
        elif '"sync"' not in r.text:
            PATH = '/data/tailf-ncs:devices?fields=device/commit-queue' \
                   '(enabled-by-default)'
            print(f"{BOLD}GET " + BASE_URL + PATH + f"{ENDC}")
            r = session.get(BASE_URL + PATH, headers=headers)
            nacq = args.ndtrans * r.text.count('true')
            print("Some devices have async cqs enabled")
    # else no devices have async cqs enabled

    # Set number of devices a transaction configures
    DEV_DATA = {"ndtrans": args.ndtrans}
    T3S_DATA = {"t3-settings": [DEV_DATA]}
    INPUT_DATA = {"t3:t3s": [T3S_DATA]}
    PATH = '/data'
    print(f"{BOLD}PATCH " + BASE_URL + PATH + f"{ENDC}")
    print(f"{HEADER}" + json.dumps(INPUT_DATA, indent=2) + f"{ENDC}")
    r = session.patch(BASE_URL + PATH, json=INPUT_DATA, headers=headers)
    print(r.text)
    print(f"Status code: {r.status_code}\n")

    # Set the amount of work done per process.
    # One "work" item equals 1s of CPU time.
    NW_DATA = {"nwork": args.nwork}
    T3S_DATA = {"t3-settings": [NW_DATA]}
    INPUT_DATA = {"t3:t3s": [T3S_DATA]}
    PATH = '/data'
    print(f"{BOLD}PATCH " + BASE_URL + PATH + f"{ENDC}")
    print(f"{HEADER}" + json.dumps(INPUT_DATA, indent=2) + f"{ENDC}")
    r = session.patch(BASE_URL + PATH, json=INPUT_DATA, headers=headers)
    print(r.text)
    print(f"Status code: {r.status_code}\n")

    # Set the transaction delay on the devices. Controls how long netsim devices
    # will sleep in the prepare phase of a transaction updating the device
    # configuration.
    DD_DATA = {"dev-delay": args.ddelay}
    T3S_DATA = {"dev-settings": [DD_DATA]}
    INPUT_DATA = {"t3:t3s": [T3S_DATA]}
    PATH = '/data'
    print(f"{BOLD}PATCH " + BASE_URL + PATH + f"{ENDC}")
    print(f"{HEADER}" + json.dumps(INPUT_DATA, indent=2) + f"{ENDC}")
    r = session.patch(BASE_URL + PATH, json=INPUT_DATA, headers=headers)
    print(r.text)
    print(f"Status code: {r.status_code}\n")

    # Call an action to calibrate CPU time used to simulate work.
    PATH = '/data/t3:t3s/calibrate-cpu-time'
    print(f"{BOLD}POST " + BASE_URL + PATH + f"{ENDC}")
    r = session.post(BASE_URL + PATH, headers=headers)
    print(r.text)
    print(f"Status code: {r.status_code}\n")

    # Run the test
    run_test(nacq, cqparam, args.ntrans, args.ndtrans)
