import json
import logging


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({'time':self.formatTime(record),'level':record.levelname,
            'logger':record.name,'event_type':getattr(record,'event_type','application'),
            'event_id':getattr(record,'event_id',None),
            'actor':getattr(record,'actor_label','System')})
