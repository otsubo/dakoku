#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: Yuki Furuta <furushchev@jsk.imi.i.u-tokyo.ac.jp>


try:
    from ghost import Ghost
    import pytz
    from apscheduler.schedulers.blocking import BlockingScheduler as Scheduler
except Exception as e:
    print "Error:", e
    print "try:"
    print "\tsudo apt-get install python-pyside python-pip"
    print "\tsudo pip install -r pip.txt"
    exit(1)
import os
import re
from datetime import datetime
import json
import urllib2
from optparse import OptionParser

# logging
import logging
LEVEL = logging.WARN
log = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setLevel(LEVEL)
log.setLevel(LEVEL)
log.addHandler(handler)


class DakokuWorker(object):
    def __init__(self, host, user, password, holidays, capture_dir=None):
        self.host = host
        self.user = user
        self.password = password
        self.holidays = holidays
        self.capture_dir = capture_dir

    def _is_same_day(self, t1, t2):
        return t1.strftime('%Y%m%d') == t2.strftime('%Y%m%d')

    def _is_holiday(self, t):
        for h in self.holidays:
            if self._is_same_day(t, h): return True
        return False

    def _login(self):
        self.g = Ghost()
        res, _ = self.g.open(self.host)
        log.debug(res)
        self.g.wait_for_page_loaded()
        res, _ = self.g.fill("form", {
            "user_id": self.user,
            "password": self.password
        })
        log.info(res)

    def work_start(self):
        if self._is_holiday(datetime.now().replace(tzinfo=pytz.timezone('Asia/Tokyo'))):
            log.info("Today is holiday! Skipping...")
            return
        self._login()
        self.g.click('input[name="syussya"]')
        self.g.wait_for_page_loaded()
        if self.capture_dir:
            capture_path = os.path.join(self.capture_dir, datetime.now().strftime('syussya_%Y-%m-%d-%H:%M:%S.jpg'))
            self.g.capture_to(capture_path)
            log.info("captured: %s", capture_path)

    def work_end(self):
        if self._is_holiday(datetime.now().replace(tzinfo=pytz.timezone('Asia/Tokyo'))):
            log.info("Today is holiday! Skipping...")
            return
        self._login()
        self.g.click('input[name="taisya"]')
        self.g.wait_for_page_loaded()
        if self.capture_dir:
            capture_path = os.path.join(self.capture_dir, datetime.now().strftime('taisya_%Y-%m-%d-%H:%M:%S.jpg'))
            self.g.capture_to(capture_path)
            log.info("captured: %s", capture_path)

class DakokuManager(object):
    def __init__(self, config_path, schedule_path):
        self.config_path = config_path
        self.schedule_path = schedule_path
        cfg = self._load_config()
        try:
            self.human_mode_min = cfg["human_mode"]
        except:
            self.human_mode_min = 0
        try:
            self.log_dir = cfg["log_dir"]
            file_handler = logging.FileHandler(os.path.join(self.log_dir, "dakoku.log"), 'a+')
            file_handler.level = LEVEL
            log.addHandler(file_handler)
            log.info("saving log to %s", self.log_dir)
        except:
            self.log_dir = None

        sched = self._load_schedule()
        start_date = datetime.strptime(sched["valid"]["start"], '%Y-%m-%d').replace(tzinfo=pytz.timezone('Asia/Tokyo'))
        end_date = datetime.strptime(sched["valid"]["end"], '%Y-%m-%d').replace(tzinfo=pytz.timezone('Asia/Tokyo'))
        holidays = self._get_holidays(start_date, end_date)
        self.worker = DakokuWorker(cfg["host"], cfg["user"], cfg["pass"], holidays, self.log_dir)
        self.register(sched["working"], start_date, end_date, holidays)

    def _load_config(self):
        with open(self.config_path, 'r') as f:
            cfg = json.load(f)
        return cfg

    def _load_schedule(self):
        with open(self.schedule_path, 'r') as f:
            cfg = json.load(f)
        return cfg
        
    def _get_holidays(self, start_date, end_date):
        pattern = re.compile("^.*basic\/([0-9]*)_.*$")
        calendar_id = 'japanese__ja@holiday.calendar.google.com'
        calendar_host = 'https://www.google.com/calendar/feeds/'
        calendar_start = '/public/basic?start-min=' + start_date.strftime('%Y-%m-%d')
        calendar_end = '&start-max=' + end_date.strftime('%Y-%m-%d')
        calendar_suffix = '&max-results=30&alt=json'
        url = calendar_host + calendar_id + calendar_start + calendar_end + calendar_suffix
        log.info("fetching holiday information from %s", url)
        raw_res = urllib2.urlopen(url)
        res = json.loads(raw_res.read())
        log.info("imported %d %s", len(res["feed"]["entry"]), " holidays")
        holidays = []
        for d in res["feed"]["entry"]:
            d_str = pattern.findall(d["id"]["$t"])[0]
            holidays.append(datetime.strptime(d_str, '%Y%m%d').replace(tzinfo=pytz.timezone("Asia/Tokyo")))
        return holidays

    def register(self, working, start_date, end_date, holidays):
        self.scheduler = Scheduler(timezone=pytz.timezone('Asia/Tokyo'), logger=log)
        for w in working:
            # schedule shukkin
            h, m = map(int, w["from"].split(':'))
            self.scheduler.add_job(self.worker.work_start, 'cron',
                                   day_of_week=w["dayOfWeek"],
                                   hour=h, minute=m,
                                   start_date=start_date,
                                   end_date=end_date,
                                   timezone=pytz.timezone('Asia/Tokyo'))
            # schedule taikin
            h, m = map(int, w["till"].split(':'))
            self.scheduler.add_job(self.worker.work_start, 'cron',
                                   day_of_week=w["dayOfWeek"],
                                   hour=h, minute=m,
                                   start_date=start_date,
                                   end_date=end_date,
                                   timezone=pytz.timezone('Asia/Tokyo'))
        self.scheduler.print_jobs()

    def start(self):
        self.scheduler.start()

    def shutdown(self):
        self.scheduler.shutdown()


if __name__ == '__main__':
    m = DakokuManager(config_path="config.json",
                      schedule_path="schedule.json")
    m.start()