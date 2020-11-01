import sqlite3
import sys, os
sys.path.append(os.path.dirname(__file__))

from datetime import datetime
from telegram_bot import main as telegram_main
from lvz_spider import main as crawler_main

#from server import URLResource
from twisted.internet import reactor
from multiprocessing import Process

FNAME = 'lvz.db'
UPDATE_TIME = 15*60 # seconds

def init_db():
   with sqlite3.connect(FNAME) as conn:
      cur = conn.cursor()
      cur.execute('''
         CREATE TABLE IF NOT EXISTS category (
            id VARCHAR PRIMARY KEY
         );
      ''')
      cur.execute('''
         CREATE TABLE IF NOT EXISTS article (
            id VARCHAR primary key,
            last_update INTEGER NOT NULL,
            status NOT NULL,
            open_till INTEGER, 
            text VARCHAR,
            category VARCHAR NOT NULL,
            title VARCHAR,
            FOREIGN KEY(category) REFERENCES category(name)
         );
      ''')
      #cur.execute('''
      #   CREATE TABLE IF NOT EXISTS bot_info (                              
      #      id VARCHAR,
      #      has_new_articles BOOLEAN,
      #      last_crawling_timestamp INTEGER
      #   )
      #''')
      #cur.execute('''
      #   INSERT INTO 
      #   bot_info (id, has_new_articles, last_crawling_timepstamp) 
      #   values (?, ?, ?)
      #''', ('lvz_bot', False, datetime.now()))
      cur.execute('''
         CREATE TABLE IF NOT EXISTS subscription (
            chat_id INTERGER,
            category VARCHAR,
            FOREIGN KEY(category) REFERENCES category(name)
         )
      ''')


if __name__ == "__main__":
   init_db()
   #site = tserver.Site(URLResource())
   #reactor.listenTCP(8080, site)
   token = "1273112480:AAH_6KWluK_n7k7jEpA_erf-6T8H_qNTvmM"
   reactor.callWhenRunning(crawler_main, FNAME, UPDATE_TIME)
   p1 = Process(target=telegram_main, args=(FNAME, token))
   #p2 = Process(target=reactor.run)
   p1.start()
   reactor.run()