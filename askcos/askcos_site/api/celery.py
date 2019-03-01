from django.http import JsonResponse
from askcos_site.celery import app

def celery_status(request):
    resp = {}
    status = {}
    stats = app.control.inspect().stats()
    active = app.control.inspect().active()
    if not stats or not active:
        return status
    worker_names = stats.keys()
    for worker in worker_names:
        name, server = worker.split('@')
        if not status.get(name):
            status[name] = {'available': 0, 'active': 0}
        status[name]['active'] += len(active[worker])
        status[name]['available'] += stats[worker]['pool']['max-concurrency'] - status[name]['active']
    status_list = []
    for key in status:
        status_list.append({
            'name': key,
            'active': status[key]['active'],
            'available': status[key]['available']
        })
    resp['queues'] = sorted(status_list, key=lambda x: x['name'])
    return JsonResponse(resp)