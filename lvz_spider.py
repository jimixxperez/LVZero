import datetime
import json
import logging
import re
import scrapy

from expiringdict import ExpiringDict

from datetime import datetime
from scrapy.http import Request
from scrapy.selector import Selector
from scrapy.crawler import CrawlerRunner

from scrapy.signalmanager import dispatcher
from twisted.internet import defer, reactor
from twisted.enterprise import adbapi
from twisted.python.failure import Failure
from tinydb import TinyDB, Query
from urllib.parse import urlparse

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

def default(o):
    if isinstance(o, (datetime.date, datetime.datetime)):
        return o.isoformat()


class ArticleItem(scrapy.Item):
    id = scrapy.Field()
    text = scrapy.Field()
    status = scrapy.Field()
    time = scrapy.Field()
    category = scrapy.Field()
    title = scrapy.Field()


class LVZSpider(scrapy.Spider):
    name = "lvz"
    urls = [
        'https://www.lvz.de'
    ]
    reg = '[0-9]{1,2}(:|.)??[0-9]{0,2}'

    def start_requests(self):
        for url in self.urls:
            yield scrapy.Request(url=url, callback=self.parse)

    def _parse_open_article(self, response):
        url = response.meta.get('url')
        path = urlparse(url).path.split('/')
        cat = path[1]
        title = path[-1].replace('-', ' ')
        t = response.meta.get('t')
        text = ' \n'.join(t for t in response.css('.pdb-article-body').css('p::text').getall())
        item = ArticleItem()
        item['id'] = url
        item['text'] = text
        item['status'] = 'open' 
        item['time'] = t
        item['category'] = cat
        item['title'] = title
        yield item

    def parse(self, response):
        not_free_urls = []
        free_urls = []
        logger.info('parsing page')
        for el in response.xpath('//span[contains(@class, "pdb-parts-paidcontent-freeuntilbadge_close")]/..').extract():
            url = Selector(text=el).css('a').xpath('@href').get()
            url = self.urls[0] + url
            not_free_urls.append(url)
            path = urlparse(url).path.split('/')
            cat = path[1]
            title = path[-1].replace('-', ' ')
            item = ArticleItem()
            item['id'] = url
            item['text'] = None
            item['status'] = 'closed'
            item['time'] = None
            item['category'] = cat
            item['title'] = title
            yield  item

        for el in response.xpath('//span[contains(@class, "pdb-parts-paidcontent-freeuntilbadge_open")]/..').extract():
            url = Selector(text=el).css('a').xpath('@href').get()
            logger.info('open article {}'.format(url))
            span_text = Selector(text=el).css(".pdb-parts-paidcontent-freeuntilbadge_open::text").get()
            time_limit = [v.group() for v in re.finditer(self.reg, span_text)]
            t = None
            if len(time_limit) == 2:
                t = (
                    datetime.now()
                        .replace(hour=int(time_limit[0]))
                        .replace(minute=int(time_limit[1]))
                )

            url = self.urls[0] + url
            yield scrapy.Request(url=url, callback=self._parse_open_article, meta={'url': url, 't': t})


runner = CrawlerRunner()


class LVZCrawler:

    def __init__(self, fname, update_time):
        self.update_time = update_time 
        self.dbpool = adbapi.ConnectionPool("sqlite3", fname)
        self.is_finished = defer.Deferred()

    @property
    def now(self):
        return int(datetime.now().timestamp())

    def _change_status_of_open_article(self, cur, item_id):
        res = cur.execute("select id from article where id = ? and status = 'open'", (item_id,))
        if res:
            cur.execute("update article set status = 'closed', last_update = ? where id = ?", (self.now, item_id,))

    def _insert_new_article(self, cur, item):
        res = cur.execute('select id from article where id = ?', (item['id'],)).fetchone()
        if not res:
            logger.info('insert new article with id {}'.format(item['id']))
            rowid = cur.execute('select rowid from category where id = ?', (item['category'],)).fetchone()
            if not rowid:
                logger.info('insert new category {}'.format(item['category']))
                cur.execute('insert into category (id) values (?)', (item['category'],))
                #rowid = cur.execute('select rowid from category where name = ?', (item['category'],)).fetchone()
            cur.execute('''
                    insert into article (id, last_update, text, status, open_till, category, title) 
                    values (?, ?, ?, ?, ?, ?, ?)
                ''', 
                (item['id'],
                self.now,
                item['text'],
                item['status'],
                int(item['time'].timestamp()),
                item['category'],
                item['title'],)
            )
    
    def _crawler_result(self, signal, item, response, spider):
        @defer.inlineCallbacks
        def do():
            logger.info('check articles')
            try:
                if item['status'] == 'closed':
                    yield self.dbpool.runInteraction(self._change_status_of_open_article, item['id'])
                else:
                    yield self.dbpool.runInteraction(self._insert_new_article, item)
            except Exception as err:
                f = Failure()
                logger.error('An error occured \n {}'.format(f.getBriefTraceback()))
        return do()

    def _spider_finished(self, spider):
        logger.info('spider finished')
        self.is_finished.callback(True)

    def start_loop(self):
        logger.info('start loop')
        self._loop()

    @defer.inlineCallbacks
    def _loop(self):
        self.is_finished = defer.Deferred()
        dispatcher.connect(self._crawler_result, signal=scrapy.signals.item_scraped)
        dispatcher.connect(self._spider_finished, signal=scrapy.signals.spider_idle)
        logger.info('start crawler')
        runner.crawl(LVZSpider)
        yield self.is_finished
        reactor.callLater(self.update_time, self._loop)

def main(fname, update_time):
    logger.info('start lvz_crawler')
    LVZCrawler(fname, update_time).start_loop()


