import argparse
import re
import sys
import os
from time import sleep
import urllib3
from urllib.parse import urlparse, parse_qs

import arrow
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from requests import Request


class PostScraper:
    def __init__(self, driver, username, password, members):
        self.driver = driver
        self.username = username
        self.password = password
        self.members = members
        self.join_date = None
        self.current_date = arrow.now()

    @staticmethod
    def parse_timestamp(timestamp):
        return arrow.get(int(timestamp)/1000)

    @staticmethod
    def format_date(date):
        return arrow.get(date).format('MM/DD/YYYY')

    def _login(self):

        """ Log in using expected credentials.  Necessary to log in to avoid CAPTCHA :( """

        self.driver.get('http://abyssc.proboards.com/')

        self.driver.find_element_by_xpath('//*[@id="login_area"]/a[2]') \
                   .click()

        self.driver.find_element_by_name('email') \
                   .send_keys(self.username)

        self.driver.find_element_by_name('password') \
                   .send_keys(self.password)

        self.driver.find_element_by_name('continue') \
                   .click()

        if self.driver.current_url == 'https://login.proboards.com/forum_submit/login':
            error = self.driver.find_element_by_class_name('errors').text or 'Unspecified problem'
            raise Exception(f"Couldn't log in!  Error: {error}")

    def _search_and_add_members(self, member):

        """ Search for a particular member by name to filter posts."""

        self.driver.find_element_by_name('who_at_least_one_placeholder').click()
        search_box = self.driver.find_element_by_name('user_search_box_input')
        search_box.send_keys(member)

        try:
            rule = EC.presence_of_element_located((By.CLASS_NAME, 'ui-selectlist-item'))
            WebDriverWait(self.driver, 10).until(rule)
        except TimeoutException:
            raise Exception(f'Couldn\'t find user {member}')

        sleep(2)
        search_box.send_keys(Keys.ENTER)

    def _search_posts_by_member(self):

        """ Fills out search menu for posts, filtering by date and member(s)."""

        self.driver.get('http://abyssc.proboards.com/search')

        for member in self.members:
            self._search_and_add_members(member)
            rule = EC.text_to_be_present_in_element((By.ID, 'user-search-0'), member)
            WebDriverWait(self.driver, 10).until(rule)

        self.join_date = self._get_member_join_dates()

        self.driver.find_element_by_xpath('/html/body/div[10]/div[11]/div/button').click()

        start_date = self.format_date(self.join_date)
        self.driver.find_element_by_xpath('//*[contains(@id,"when_between_start_input")]') \
                   .send_keys(start_date)

        end_date = self.format_date(self.current_date)
        self.driver.find_element_by_xpath('//*[contains(@id,"when_between_end_input")]') \
                   .send_keys(end_date)

        self.driver.find_element_by_name('search').click()

    def _get_member_join_dates(self):

        """ Grabs the user link generated when searching for users to filter, goes to their profile page,
        and scrapes off their join date.  We want to filter the search results starting when a user joined,
        rather than some arbitrary date.  In the case of multiple users, we want the earliest join date."""

        minimum_join_date = arrow.utcnow()
        for link in self.driver.find_elements_by_xpath('//*[@id="user-search-0"]//*/a'):
            href = link.get_attribute('href')
            self.driver.execute_script(f'window.open("{href}", "_blank")')

            self.driver.switch_to.window(self.driver.window_handles[-1])

            join_date = self.driver.find_element_by_xpath('//td/abbr[@class="o-timestamp time"]')\
                                   .get_attribute('data-timestamp')

            join_date = self.parse_timestamp(join_date)

            if join_date < minimum_join_date:
                minimum_join_date = join_date

            self.driver.close()
            self.driver.switch_to.window(self.driver.window_handles[0])

        return minimum_join_date

    def _scrape_posts(self, numbers):

        """ For each post on a page, get the timestamp, thread name, thread ID, and message."""

        for post in self.driver.find_elements_by_tag_name('article'):
            timestamp = post.find_element_by_class_name('o-timestamp') \
                            .get_attribute('data-timestamp')

            link = post.find_element_by_tag_name('a')
            thread_name = link.text
            thread_id = numbers.findall(link.get_attribute('href'))[0]

            text = post.find_element_by_class_name('message').get_attribute('innerHTML')

            yield {'timestamp': timestamp, 'thread_name': thread_name, 'thread_id': thread_id, 'text': text}

    def _continue_to_next_page(self):

        """ Either click to the next page or issue a new search with different date parameters (there's a
         limit of how many posts can be returned in one query. """

        next_button = self.driver.find_element_by_class_name('ui-pagination') \
                                 .find_elements_by_tag_name('li')[-1]

        if 'state-disabled' in next_button.get_attribute('class'):
            timestamps = []
            for date in self.driver.find_elements_by_css_selector('article > * > abbr'):
                ts = self.parse_timestamp(date.get_attribute('data-timestamp'))
                timestamps.append(ts)

            self.current_date = arrow.get(min(timestamps))
            self._issue_new_search()

        else:
            next_button.click()

        return True

    def _issue_new_search(self):

        """ Issue a new search by replacing the date and page parameters in the URL. """

        url = urlparse(driver.current_url)

        qs = parse_qs(url.query)

        qs['when_between_start'] = self.format_date(self.join_date)
        qs['when_between_end'] = self.format_date(self.current_date)
        qs['page'] = 1

        new_url = Request('GET', f'{url.scheme}://{url.netloc}{url.path}', params=qs).prepare()

        print(f'Issuing new search for posts on and before {self.current_date}...')

        return self.driver.get(new_url.url)

    def _scrape_all_posts(self):

        """ Scrapes all posts on a page and then query for more, going backwards.
        Stops when the current searching date is earlier than minimum join date."""

        numbers = re.compile('\d+')

        current_url = driver.current_url

        print('Searching...')
        while True:
            try:
                yield from self._scrape_posts(numbers)

                self._continue_to_next_page()

                sleep(1.75)

                if self.current_date.date() <= self.join_date.date():
                    print('Reached the end!')
                    self.driver.close()
                    break

            except urllib3.exceptions.ProtocolError:
                print('ProtocolError.  Trying again...')
                sleep(3)
                self.driver.get(current_url)
            except WebDriverException:
                print('WebDriverException.  Trying again...')
                sleep(3)
                self.driver.get(current_url)

    def scrape(self):
        self._login()
        self._search_posts_by_member()
        return self._scrape_all_posts()


def parse_args(args):

    parser = argparse.ArgumentParser(description='Scrapes posts from ProBoards forum')
    parser.add_argument('driver_path', help='Path of webdriver')
    parser.add_argument('username', help='Username for login')
    parser.add_argument('password', help='Password for login')
    parser.add_argument('members', help='Members to search', nargs='+')

    return parser.parse_args(args)


if __name__ == "__main__":

    args = parse_args(sys.argv[1:])

    driver = webdriver.Chrome(args.driver_path)
    p = PostScraper(driver, args.username, args.password, args.members)
    posts = p.scrape()

    if not os.path.exists('data'):
        os.mkdir('data')

    with open(os.path.join('data', 'all_posts.csv'), 'w') as f:
        f.write('~|~'.join(['timestamp', 'thread_name', 'thread_id', 'text'])+'\n')
        for post in posts:
            f.write('~|~'.join(post.values())+'\n')
