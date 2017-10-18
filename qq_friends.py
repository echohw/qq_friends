#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# Created on 2017-10-15 10:22:35
# Project: qq_friends

import re
import time
import random
import logging
from bs4 import BeautifulSoup
from pymongo import MongoClient
from bson.objectid import ObjectId
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import StaleElementReferenceException
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

USER_AGENTS_MOBILE = [
    "Mozilla/5.0 (Linux; Android 5.1.1; Nexus 6 Build/LYZ28E) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/48.0.2564.23 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; U; Android 6.0.1; zh-cn; MI 4LTE Build/MMB29M) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/53.0.2785.146 Mobile Safari/537.36 XiaoMi/MiuiBrowser/9.0.3"
]


def save_to_mongo(results, collection, DB="pyspider"):  # 保存到mongo数据库
    client = MongoClient("127.0.0.1", 27017)
    db = client[DB]
    db[collection].insert(results)


def get_driver(type="Chrome"):
    userAgent = random.choice(USER_AGENTS_MOBILE)
    if (type == "PhantomJS"):
        dcap = dict(DesiredCapabilities.PHANTOMJS)
        dcap["phantomjs.page.settings.loadImages"] = False  # 禁止加载图片
        dcap["phantomjs.page.settings.userAgent"] = (userAgent)
        driver = webdriver.PhantomJS(desired_capabilities=dcap)
    elif (type == "Chrome"):
        options = webdriver.ChromeOptions()
        prefs = {
            'profile.default_content_setting_values': {  # 设置不加载图片
                'images': 2
            }
        }
        options.add_experimental_option('prefs', prefs)
        options.add_argument('"user-agent"="%s"' % userAgent)
        driver = webdriver.Chrome(chrome_options=options)
    return driver


def qzone_login(driver, username, password):  # 手机版qq空间登录
    driver.get("http://i.qq.com")  # 浏览器地址定向为qq登陆页面
    time.sleep(0.2)
    driver.find_element_by_id('u').clear()
    driver.find_element_by_id("u").send_keys(username)  # 向输入框发送用户名
    driver.find_element_by_id('p').clear()
    driver.find_element_by_id("p").send_keys(password)  # 发送密码
    pre_url = driver.current_url  # 保存登录前的url
    flag = False
    for i in range(5): # 登录失败的重试次数
        try:
            driver.find_element_by_id("go").click() # 模拟点击登录按钮
        except:
            pass
        time.sleep(2)
        if driver.current_url == pre_url:  # 若两次的地址栏一样,说明登录未成功
            print("失败")
            flag = False
        else:
            print("登录成功")
            flag = True
            break
    if not flag:
        input("登录失败，请手动登录，登录成功后请点击Enter键:")


def fetch_more(driver):  # 查看更多
    hostuin = True if "hostuin" in driver.current_url else False  # 判断页面类型
    try:
        if (hostuin and driver.find_element_by_css_selector("#page-mine > div.auth") != None):  # 无权限或未开通
            return
    except NoSuchElementException:
        pass
    scroll = "window.scrollTo(0,document.body.scrollHeight)"
    flag = "无更多内容" if hostuin else "已加载全部"
    for i in range(800): # 设置最多执行下拉刷新的次数
        print(i)
        try:
            try:
                if hostuin:
                    more = driver.find_element_by_css_selector("#feeds_more_mine")
                else:
                    more = driver.find_element_by_css_selector("#feeds_more_ic > span")
                if (hasattr(more, "text") and flag in more.text): # 判断页面中是否存在某个字符串来决定是否继续下拉刷新(也可判断一定次数内页面长度是否改变)
                    print(flag)
                    break
            except NoSuchElementException:
                pass
            except StaleElementReferenceException:
                pass
            driver.execute_script(scroll)
            if (len(driver.current_url) > 500):  # 对url进行判断是否进入了详情页面,如果是则回退
                print("详情页面")
                driver.back()
            try:
                if hostuin:
                    more = driver.find_element_by_css_selector("#feeds_more_mine")
                else:
                    more = driver.find_element_by_css_selector("#feeds_more_ic > button")
                if (hasattr(more, "click")):
                    more.click()
            except NoSuchElementException:
                pass
            except WebDriverException:
                pass
        except Exception as e:
            logging.exception(e)
        time.sleep(0.3) # 睡眠0.3s等待页面加载
    return driver.page_source


def get_cur_time():  # 获取当前的时间(毫秒)
    return int(round(time.time() * 1000))


def parse(page_source, username, friends_dic={}):  # 解析个人动态页面,传入页面代码,返回好友关系字典
    soup = BeautifulSoup(page_source, "html.parser")
    friends = soup.select("div.feed.dataItem")
    for friend in friends:  # 提取页面中的所有动态信息
        sender_info = friend.select("div.feed-hd > div.info > p.title > span")[0]
        sender = sender_info["data-params"]  # 获取发送者的qq号
        sender_nickname = sender_info.text  # 获取发送者的昵称
        if (not friends_dic.get(sender)):  # 判断发送者是否在字典中,如果没有则初始化发送者
            friends_dic[sender] = {}
            friends_dic[sender][sender] = sender_nickname  # 添加发送者本人信息
        likes = friend.select("div.feed-ft.js-feedft > div.likes.j-likelist > a")
        for like in likes:
            friends_dic[sender][like["data-params"]] = like.text  # 从点赞中提取数据
        comments = friend.select("div.feed-ft.js-feedft > div.comments.min-comments > div > div.comment-item")
        for comment in comments:  # 从评论中提取数据
            data_params = comment["data-params"]
            try:
                reply, nickname = re.findall(r"uin=(\d+).*?nick=(.*)", data_params)[0]  # 提取回复人信息
                friends_dic[sender][reply] = nickname  # 保存回复人信息
            except Exception as e:
                logging.exception(e)
            reply_list = comment.select("div.mainer > ul.reply-list > li.item")  # 从回复列表中提取
            for li in reply_list:
                data_params = li["data-params"]
                try:
                    nickname, reply = re.findall(r"nick=(.*?)&uin=(\d+)", data_params)[0]
                    friends_dic[sender][reply] = nickname  # 保存回复人信息
                except Exception as e:
                    logging.exception(e)
    if (not friends_dic.get(username)):
        friends_dic[username] = {}
        friends_dic[username][username] = ""  # 添加个人信息
    for number in friends_dic:
        if (number != username):
            friends_dic[username][number] = friends_dic[number][number]
    return friends_dic


def parse_hostuin(page_source, friends_dic={}):
    soup = BeautifulSoup(page_source, "html.parser")
    items = soup.select("div.feed.dataItem")
    for item in items:
        sender_info = item.select("div.hd > p > a")[0]
        sender = sender_info["data-params"]  # 获取发送者的qq号
        sender_nickname = sender_info.text  # 获取发送者的昵称
        if (not friends_dic.get(sender)):  # 判断发送者是否在字典中,如果没有则初始化发送者
            friends_dic[sender] = {}
            friends_dic[sender][sender] = sender_nickname  # 添加发送者本人信息
        likes_and_comments = item.select("div.ft > div.min-comments > p > a.fn")
        for lac in likes_and_comments:
            friends_dic[sender][lac["data-params"]] = lac.text  # 从点赞中提取数据 # KeyError
    return friends_dic


friends_dic = {  # 定义全局的字典,数据格式为
    # "111111":{
    #     "111111":"昵称", # 好友列表
    #     "222222":"昵称",
    # },
}
driver = get_driver()
username = "用户名"
password = "密码"
qzone_login(driver, username, password)  # 登录进入个人动态页面
page_source = fetch_more(driver)  # 查看更多,返回页面代码或None
parse(page_source, username, friends_dic)  # 解析个人动态页面,传入全局的字典,数据都将会被保存到全局的字典中,否则每个页面都将会返回一个新字典

url_format = "https://h5.qzone.qq.com/mqzone/profile?starttime=%s&hostuin=%s"
driver.get(url_format % (get_cur_time(), username))  # 跳转到我的个人主页进行抓取
page_source = fetch_more(driver)  # 查看更多,返回页面代码
parse_hostuin(page_source, friends_dic)

for number in friends_dic[username]:  # 从已抓取的我的好友列表中提取数据,提取TA们的好友信息
    if (number != username):
        driver.get(url_format % (get_cur_time(), number))
        page_source = fetch_more(driver)
        if (page_source != None):
            parse_hostuin(page_source, friends_dic)
    print(friends_dic)

# 程序执行完毕将数据存入mongo数据库
for number, fds in friends_dic.items():  # 将字典中的数据分别存入mongo数据库
    save_to_mongo({number, fds}, "qzone")
