#!/usr/bin/env python
# coding=utf-8

#---------------------------------------------------------
# Name:         Tomcat错误日志发送邮件脚本
# Purpose:      收集Tomcat异常日志并发送Flume
# Version:      1.0
# Author:       Alex
# Created:      2015-11-18
# Copyright:    ohoh
# Python：       2.7~
#--------------------------------------------------------

import os
import sys
from os.path import getsize
from sys import exit
import pycurl
import StringIO
import json
import urllib
import datetime
import time
from multiprocessing import Process
from multiprocessing import Pool,Manager
from re import compile, IGNORECASE

#配置采集信息
config = [
    {
    'host':'localhost',
    'servertype':'tomcat',
    'ip':'localhost',
    'path':'/data/work/app/logprog/logs/',
    'filename':'a.out',
    'desc':'pick out error info from tomcat log file',
    'type':'error'
    },
    {'host':'localhost',
    'servertype':'tomcat',
    'ip':'localhost',
    'path':'/data/work/app/logprog/logs/',
    'filename':'access_2015-11-16.log',
    'desc':'pick out login ip info from tomcat access log file',
    'type':'access'
    }
]

#flume server http source url
#url = "http://172.16.0.146:50035/"
url = "http://101.200.234.147:50004/"


#匹配的错误信息关键字的正则表达式
pattern_begin = compile(r'threw exception|^\t+\bat\b',IGNORECASE)
pattern_end = compile(r'^\n',IGNORECASE)

pattern_begin = compile(r'^\[ERROR',IGNORECASE)
pattern_end = compile(r'^\[',IGNORECASE)


#写入本次日志文件的本次位置
def write_this_position(file,last_positon):
    try:
        data = open(file,'w')
        data.write(str(last_positon))
        data.write('\n' + "Don't Delete This File,It is Very important for Looking Tomcat Error Log !! \n")
        data.close()
    except:
        print "Can't Create File !" + file
        exit()
        
#读取上一次日志文件的读取位置
def get_last_position(file):
    try:
        
        if not os.path.isfile(tomcat_log):
            write_this_position(file, 0)
            
        data = open(file,'r')
        last_position = data.readline()
        if last_position:
            last_position = int(last_position)
        else:
            last_position = 0
    except:
        last_position = 0

    return last_position


def getCurrentDay():
	return (datetime.date.today()).strftime("%Y%m%d")


#分析文件找出异常的行
def analysis_log(item):
    
    currentDay = getCurrentDay()

    errorbodystr = ''
    errorlist = []                                         #定义一个列表，用于存放错误信息.
    logfilename = item['path'] + item['filename']
    try:
        data = open(logfilename,'r')
    except:
        exit()
    #该文件是用于记录上次读取日志文件的位置,执行脚本的用户要有创建该文件的权限
    last_position_logfile = '../conf/' + item['filename'] + '.conf'
    
    last_position = get_last_position(last_position_logfile) #得到上一次文件指针在日志文件中的位置
    this_postion = getsize(tomcat_log)                      #得到现在文件的大小，相当于得到了文件指针在末尾的位置
    if this_postion < last_position:                        #如果这次的位置 小于 上次的位置说明 日志文件轮换过了，那么就从头开始
        data.seek(0)
    elif this_postion == last_position:                     #如果这次的位置 等于 上次的位置 说明 还没有新的日志产生
        exit()
    elif this_postion > last_position:                      #如果是大于上一次的位置，就移动文件指针到上次的位置
        data.seek(last_position)

    lineindex = 0
    in_error_body_flag = False
    end_error_flag  = False
    for line in data:
        #match error flag
        lineindex += 1

        begin_error_flag = pattern_begin.search(line) is not None
        if begin_error_flag:
            #match error flag and set in error flag is true
            in_error_body_flag = True
            errorTime = line.split(" ")[1:3]
            #insert a error body line into list
            #errorlist.append(line)
            errorbodystr += line
            continue
        else:
            #match end error body flag
            end_error_flag = pattern_end.search(line) is not None
            if  in_error_body_flag and end_error_flag:
                in_error_body_flag = False
                #match error flag and set in error flag is true
                in_error_body_flag = False
                end_error_flag  = False   #end a error body
                error_flag = False        #end a error end flag

                #format json body dict
                errorInfoDict = {}
                errorInfoDict['currentday'] = int(currentDay)
                errorInfoDict['infoserver'] = item['servertype']
                errorInfoDict['infotype'] = item['type']
                errorInfoDict['infotime'] = " ".join(errorTime)
                errorInfoDict['body'] = errorbodystr
                errorInfoDict['host'] = item['host']
                errorInfoDict['ip'] = item['ip']
                #print datetime.datetime.now() ,errorInfoDict
                #destory errorlist
                errorlist.append(errorInfoDict)
                del errorInfoDict 

                continue
            elif in_error_body_flag :
                errorbodystr += line
                continue

        #not error body  then continue   to find
        if not in_error_body_flag:
            #not error and not error body  then continue   find
            continue



    print datetime.datetime.now() ,'parse log over'
    write_this_position(last_position_logfile,data.tell())  #写入本次读取的位置
    data.close()

    return errorlist                              #形成一个字符串

def main(logToFlumeList,opertime):
    print datetime.datetime.now(),'begin post batch json data to http source ' ,len(logToFlumeList)
    crl = pycurl.Curl()
    crl.setopt(pycurl.VERBOSE,1)
    crl.setopt(pycurl.FOLLOWLOCATION, 1)
    crl.setopt(pycurl.MAXREDIRS, 5)
    #crl.setopt(pycurl.AUTOREFERER,1)

    crl.setopt(pycurl.CONNECTTIMEOUT, 60)
    crl.setopt(pycurl.TIMEOUT, 300)
    #crl.setopt(pycurl.PROXY,proxy)
    crl.setopt(pycurl.HTTPPROXYTUNNEL,1)
    #crl.setopt(pycurl.NOSIGNAL, 1)
    crl.fp = StringIO.StringIO()
    crl.setopt(pycurl.USERAGENT, "ohoh")

    """
    post_data_dic = '[{"body": "{fieldB:99999,fieldA:888888,fieldC:12221}"}]'
    post_data_dic = '[{"body": "{fieldB:99999,fieldA:888888,fieldC:\'12221\'}"}]'
    post_data_dic = [{"body": "{'fieldB':888899999,'fieldA':888888,'fieldC':'12221'}"}]
    """
    print datetime.datetime.now(),'start post batch json data to http source '
    for item in logToFlumeList:
        data = {}
        data["body"] = str(item)

        post_data_dic  = []
        post_data_dic.append(data)
        post_data_dic  = str(post_data_dic)
        #print datetime.datetime.now() ,'post data is ' ,post_data_dic
        #print
        # Option -d/--data <data>   HTTP POST data
        #crl.setopt(crl.POSTFIELDS,  urllib.urlencode(post_data_dic))
        crl.setopt(crl.POSTFIELDS,  post_data_dic)

        crl.setopt(pycurl.URL, url)
        crl.setopt(crl.WRITEFUNCTION, crl.fp.write)
        crl.perform()
        #print crl.fp.getvalue()
        del data
        del post_data_dic

    print datetime.datetime.now(),'end post batch json data to http source ' ,len(logToFlumeList)

if __name__ == '__main__':
    for item in config:
        #parse tomcat log ,return capture info list
        tomcat_log = item['path'] + item['filename']
        if not os.path.isfile(tomcat_log):
            print datetime.datetime.now() ,'config error ,log file is not exists ,please check !'
            sys.exit(0)
            
        #parse error type log info
        if item['type'] == 'error':
            logToFlumeList = analysis_log(item)
        #parse access type log info
        elif item['type'] == 'access':
            logToFlumeList = []
            pass
        
        if len(logToFlumeList) == 0 :
            print datetime.datetime.now() ,' not found capture infor in tomcat log file ' ,tomcat_log
            sys.exit(0)
            
        main(logToFlumeList,str(datetime.datetime.now()))
         
    """    
    processNumber = 2
    pool = Pool(processNumber)
    processList = []
    for process in range(processNumber):
        p = pool.apply_async(main, (logToFlumeList,str(datetime.datetime.now())))
        processList.append(p)
    while 1:
        try:
            time.sleep(5)
            status = True
            for item in processList:
                status = status and item.ready()
                if status:
                    break
        except KeyboardInterrupt:
            print datetime.datetime.now(),"process pool run error"
            pool.terminate()
            pool.wait(None)
            break

    for item in processList:
        item.wait()
    pool.close()
    pool.join()
    del pool
    del processList
    """
