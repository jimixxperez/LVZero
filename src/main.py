
import argparse
import configparser
import sqlite3
import sys, os
sys.path.append(os.path.dirname(__file__))

from datetime import datetime
from telegram_bot import main as telegram_main
from lvz_spider import main as crawler_main

from twisted.internet import reactor
from multiprocessing import Process

def init_db(fname):
   with sqlite3.connect(fname) as conn:
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
      cur.execute('''
         CREATE TABLE IF NOT EXISTS subscription (
            chat_id INTERGER,
            category VARCHAR,
            FOREIGN KEY(category) REFERENCES category(name)
         )
      ''')

def main():
   config = configparser.ConfigParser()
   parser = argparse.ArgumentParser(description='lvz+ crawler.')
   parser.add_argument('cfg', type=str, help='provide config of type ini.')
   config.read(parser.parse_args().cfg)
   token = config['DEFAULT']['token']
   fpath = config['DEFAULT']['sqlite_db']
   update_time = int(config['DEFAULT']['update_time'])
   init_db(fpath)
   reactor.callWhenRunning(crawler_main, fpath, update_time)
   p1 = Process(target=telegram_main, args=(fpath, token))
   p1.start()
   reactor.run()

if __name__ == "__main__":
   main()
