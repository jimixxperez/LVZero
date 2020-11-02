#!/usr/bin/env python
# -*- coding: utf-8 -*-
# This program is dedicated to the public domain under the CC0 license.

import logging
import sqlite3
import urllib3

#telegram.api._pools = {
#    'default': urllib3.PoolManager(num_pools=3, maxsize=10, retries=3, timeout=30)
#}

from datetime import datetime, timedelta
from telegram import (
    Poll,
    ParseMode,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButtonPollType,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    JobQueue,
    PollAnswerHandler,
    PollHandler,
    MessageHandler,
    Filters,
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)


class Handler:

    def __init__(self, fname):
        self.fname = fname
        self.last_subscription_update = self.now

    @property
    def now(self):
        return int(datetime.now().timestamp())

    def start(self, update, context):
        """Inform user about what this bot can do"""
        update.message.reply_text(
            'Dieser Bot schickt Links/Informationen zu offenen LVZ+ Artikeln\n'
            'Folgenden Aktionen sind möglich: \n'
            '\t 1. /open ... schickt Links zu gerade offnen Artikeln. \n'
            '\t 2. /sub ... schickt regelmäßige Updates zu offnen Artikeln. \n'
            '\t 2. /unsub ... stoppt den /sub . \n'
        )

    def subscribe(self, update, context):
        """send lvz categories"""
        logger.info('received')
        with sqlite3.connect(self.fname) as conn:
            categories = conn.cursor().execute('select id from category').fetchall()
        categories = [c[0] for c in categories]
        categories.append('Alle')

        # telegram poll requires at least 2 options
        if len(categories) < 2:
            update.message.reply_text(
                'Noch keine Kategorien in der Datenbank \n'
                'Bitte versuche es später schauen.'
            )
            return

        message = context.bot.send_poll(
            update.message.chat.id,
            "Welche Kategorien?",
            categories,
            is_anonymous=False,
            allows_multiple_answers=True,
        )
        # Save some info about the poll the bot_data for later use in receive_poll_answer
        payload = {
            message.poll.id: {
                "categories": categories,
                "message_id": message.message_id,
                "chat_id": update.effective_chat.id,
                "answers": 0,
            }
        }
        context.bot_data.update(payload)

    def receive_subscription(self, update, context):
        """Summarize a users poll vote"""
        logger.info('received sub poll')
        answer = update.poll_answer
        poll_id = answer.poll_id
        try:
            categories = context.bot_data[poll_id]["categories"]
        ## this means this poll answer update is from an old poll, we can't do our answering then
        except KeyError:
            return
        selected_options = answer.option_ids
        chat_id = context.bot_data[poll_id]['chat_id']
        inserts = [(chat_id, categories[idx]) for idx in selected_options]
        logger.info('received following options from {}'.format(selected_options))
        with sqlite3.connect(self.fname) as conn:
            cur = conn.cursor()
            cur.execute('delete from subscription where chat_id = ?', (chat_id,))
            cur.executemany('insert into subscription values (?, ?)', inserts) 
        #answer_string = ""
        #for question_id in selected_options:
        #    if question_id != selected_options[-1]:
        #        answer_string += questions[question_id] + " and "
        #    else:
        #        answer_string += questions[question_id]
        #context.bot.send_message(
        #    context.bot_data[poll_id]["chat_id"],
        #    "{} feels {}!".format(update.effective_user.mention_html(), answer_string),
        #    parse_mode=ParseMode.HTML,
        #)
        #context.bot_data[poll_id]["answers"] += 1
        ## Close poll after three participants voted
        #if context.bot_data[poll_id]["answers"] == 3:
        context.bot.stop_poll(
            context.bot_data[poll_id]["chat_id"], context.bot_data[poll_id]["message_id"]
        )
        context.bot.sendMessage(
            chat_id, 
            'Erfolgreich {} gesubbed.'.format(', '.join([c[1] for c in inserts]))
        )

    def unsubscribe(self, update, context):
        chat_id = update.message.chat_id
        with sqlite3.connect(self.fname) as conn:
            cur = conn.cursor()
            cur.execute('delete from subscription where chat_id = ?', (chat_id,))

        update.message.reply_text(
            'Erfolgreich unsubbed.'
        )

    def current(self, update, context):
        with sqlite3.connect(self.fname) as conn:
            cur = conn.cursor()
            cur.execute("""
                select 
                    a.id, c.id, a.open_till, a.title
                from article a
                join category c on a.category = c.id 
                where status='open' and a.open_till > ?
                order by c.id, a.open_till
            """, (self.now,))
            res = cur.fetchall()

        if not res:
            update.message.reply_text(
                'Momentan keine offenen Artikeln.'
            )
        else:
            infos = {}
            for l, c, t, title in res:
                t = datetime.fromtimestamp(t).strftime('%H:%M')
                infos.setdefault(c, [])
                infos[c].append({'l': l, 't': t, 'title':title})

            #infos = [
            #    {
            #        'l': r[0], 
            #        'c': r[1], 
            #        't': datetime.fromtimestamp(r[2]).strftime('%H:%M'),
            #        'title': r[3]
            #    }
            #    for r in res 
            #]
            logger.info(infos)
            update.message.reply_text('Offene Artikel')
            for cat, info in infos.items():
                update.message.reply_text(
                    cat,
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton(text='{t}-{title}'.format(**v), url=v['l'])
                        ] for v in info
                    ])
                )

    def check_new_entries(self, context):
        logger.info('checking new entries for subscription')
        with sqlite3.connect(self.fname) as conn:
            cur = conn.cursor()
            last_sub_update = self.last_subscription_update
            self.last_subscription_update = self.now
            res = cur.execute('''
                select
                    s.chat_id, a.id, a.category, a.open_till, a.title 
                from subscription s
                join article a on a.category = s.category
                where a.open_till > ? and a.status = 'open' and a.last_update > ?
                order by s.chat_id
            ''', (self.now, last_sub_update)).fetchall()
        if not res:
            logger.info('nothing new')
            return 

        data = {}
        for chat_id, l, c, t, title in res: 
            data.setdefault(chat_id, {})
            data[chat_id].setdefault(c, [])
            t = datetime.fromtimestamp(t).strftime('%H:%M')
            data[chat_id][c].append({'l': l, 't': t, 'title': title})

        logger.info('new entries found {}'.format(data))

        for chat_id, val in data.items():
            for cat, info in val.items():
                context.bot.sendMessage(
                    chat_id,
                    text=cat,
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton(text='{t}-{title}'.format(**v), url=v['l'])
                        ] for v in info
                    ])
                )


    def help_handler(self, update, context):
        """Display a help message"""
        update.message.reply_text("Benutze /open, /sub oder /unsub um Aktionen durchzuführen")


def main(fname, token):
    updater = Updater(token, use_context=True)
    sub_update_time = timedelta(minutes=1)
    handler = Handler(fname)
    dp = updater.dispatcher
    job_queue = JobQueue()
    job_queue.set_dispatcher(dp)
    job_queue.run_repeating(handler.check_new_entries, first=0, interval=sub_update_time)
    job_queue.start()
    dp.add_handler(CommandHandler('start', handler.start))
    dp.add_handler(CommandHandler('open', handler.current))
    dp.add_handler(CommandHandler('sub', handler.subscribe))
    dp.add_handler(CommandHandler('unsub', handler.unsubscribe))
    dp.add_handler(PollAnswerHandler(handler.receive_subscription))
    dp.add_handler(CommandHandler('help', handler.help_handler))

    # Start the Bot
    updater.start_polling()

    # Run the bot until the user presses Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT
    updater.idle()


if __name__ == '__main__':
    main('lvz.db')