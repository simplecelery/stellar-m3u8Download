import os
import sys
import time
import requests
from . import pyaes
from . import m3u8
import urllib3
import json
import threading
import queue
from urllib.parse import urlparse


def bytesToHexString(data):
    temp = []
    for i in data:
        temp.append('0x%02X' % i)
    return temp

class hlsDownloader:
    def __init__(self):
        urllib3.disable_warnings()
        self.m3u8Url = ''
        self.savePath = ''
        self.medianame = ''
        self.tryCount = 10
        self.key = None
        self.keyText = None
        self.keyVI = None
        self.host = ''
        self.TsInfo = None
        self.fout = None
        self.taskQue = queue.Queue(10)
        self.downpercent = '0%'
        self.downedsuccess = '0%'
        self.downstate = 0
        self.stopdown = False
        
    def stop(self):
        self.stopdown = True
        #self.taskQue.join()
        print('hls down stop')
        
    def setmedianame(self,name):
        self.medianame = name
        
    def putQueue(self,tasklist):
        cancled = False
        for task in tasklist:
            if self.stopdown == False:
                self.taskQue.put(task)
            else:
                self.taskQue.put(None)
                cancled = True
                break;
        if cancled:
            print('down cancle')
            self.downstate = -1
        else:
            print('down end')
            self.downstate = 2
            self.downpercent = '100%'
        self.taskQue.join()
        print('putQueue end ' + str(self.downstate))
        
    def getQueue(self,tasklen):
        n = 0
        m = 0
        while self.downstate == 1:
            task = self.taskQue.get()
            if task == None:
                self.taskQue.task_done()
                break;
            downres = self.downTsFile(task)
            self.downpercent = '%.2f%%' % ((task['index'] / tasklen) * 100)
            if downres == 1:
                n = n + 1
            m = m + 1
            self.downedsuccess = '%.2f%%' % ((n / m) * 100)
            #self.saveInfoToJson()
            self.taskQue.task_done()
        if self.fout:
            self.fout.close()
        self.saveInfoToJson()
        print('getQueue end')
        
    def openM3u8Url(self,url):
        self.m3u8Url = url
        self.parserUrl()
    
    def downToFile(self,path):
        self.stopdown = False
        self.savePath = path
        self.fout = open(self.savePath, "ab")
        if self.fout == None:
            return
        self.downstate = 1
        alltsnum = len(self.TsInfo['tsfiles'])
        self.t1 = threading.Thread(target=self.putQueue, args=(self.TsInfo['tsfiles'],))
        self.t1.start()
        self.t2 = threading.Thread(target=self.getQueue, args=(alltsnum,))
        self.t2.start()
        
    def downTsFile(self,tsinfo):
        if tsinfo['downstate'] == 1:
            return 1
        tryCount = self.tryCount
        tsurl = tsinfo['url']
        data = None
        state = -1
        while True:
            if self.stopdown:
                return 0
            if tryCount < 0:
                print("\t{0}下载失败！".format(tsurl))
                break
            tryCount = tryCount - 1
            try:
                response = requests.get(tsurl, timeout=20, stream=True, verify=False)
                if response.status_code == 200:
                    data = response.content
                    state = 1
                    break
            except:
                print("\t{0}下载失败！正在重试".format(tsurl))
        self.onTsDownload(tsinfo,data,state)
        return state
    
    def onTsDownload(self,tsinfo,data,state):
        listlen = len(self.TsInfo['tsfiles'])
        if self.fout == None:
            return
        if state == 1:
            if self.key != None:
                while len(data):
                    self.fout.write(self.key.decrypt(data[:16]))
                    data = data[16:]
            else:
                datastart = 0
                if len(data) > 14:
                    if data[0] == 0x42 and data[1] == 0x4d and data[6] == 0 and data[7] == 0 and data[8] == 0 and data[9] == 0:
                        datastart = 14
                if len(data) > 8:
                    if data[0] == 0x89 and data[1] == 0x50 and data[2] == 0x4E and data[3] == 0x47 and data[4] == 0x0D and data[5] == 0x0A and data[6] == 0x1A and data[7] ==  0x0A:
                        datastart = 8
                self.fout.write(data[datastart:])
        self.TsInfo['tsfiles'][tsinfo['index']]['downstate'] = state
    
    def saveInfoToJson(self):
        jsondata = {}
        jsondata['savepath'] = self.savePath
        jsondata['m3u8url'] = self.m3u8Url
        jsondata['tsinfo'] = self.TsInfo
        jsondata['keytext'] = self.keyText
        jsondata['keyvi'] = self.keyVI
        jsondata['downpercent'] = self.downpercent
        jsondata['downedsuccess'] = self.downedsuccess
        jsondata['name'] = self.medianame
        jsonfile = self.medianame + '.json'
        with open(jsonfile, 'w') as fp:
            json.dump(jsondata, fp)
            print('saveInfoToJson')
            fp.close()
    
    def loadInfoFromJson(self,file):
        file = open(file, "rb")
        jsondata = json.loads(file.read(), strict = False)
        file.close()
        if jsondata:
            self.medianame = jsondata['name']
            self.savePath = jsondata['savepath']
            self.m3u8Url = jsondata['m3u8url']
            self.TsInfo = jsondata['tsinfo']
            self.keyText = jsondata['keytext']
            self.keyVI = jsondata['keyvi']
            self.downpercent = jsondata['downpercent']
            self.downedsuccess = jsondata['downedsuccess']
            if self.keyText != None:
                if self.keyVI != None:
                    self.key = pyaes.AESModeOfOperationCBC(bytes(self.keyText, encoding='utf8'), bytes(key.iv, encoding='utf8'))
                else:
                    self.key = pyaes.AESModeOfOperationCBC(bytes(self.keyText, encoding='utf8'))
        
    def parserUrl(self):
        hlsInfo,host,rootpath = self.parserM3u8(self.m3u8Url)
        self.TsInfo = self.getTsInfo(hlsInfo,host,rootpath)
        self.key = self.loadKey(hlsInfo,host,rootpath)

    def parserM3u8(self,hlsurl):
        tryCount = self.tryCount
        rootUrlPath = hlsurl[0:hlsurl.rindex('/')] + '/'
        x = urlparse(hlsurl)
        host = x.scheme + '://' + x.hostname
        if x.port:
            host = host + ':' + str(x.port)
        while True:
            if tryCount < 0:
                print("\t{0}下载失败！".format(hlsurl))
                return None,host,rootUrlPath
            tryCount = tryCount - 1
            try:
                response = requests.get(hlsurl, timeout=20,verify=False)
                if response.status_code == 301:
                    nowM3u8Url = response.headers["location"]
                    print("\t{0}重定向至{1}！".format(hlsurl, nowM3u8Url))
                    hlsurl = nowM3u8Url
                    continue
                break
            except:
                print("\t{0}下载失败！正在重试".format(hlsurl))
        m3u8Info = m3u8.loads(response.text)
        if m3u8Info.is_variant:
            print("\t{0}为多级码流！".format(hlsurl))
            for rowData in response.text.split('\n'):
                if rowData.find(".m3u8") > 0:
                    if rowData.find('://') >= 0:
                        hlsurl = rowData
                    else:
                        if rowData[0] == '/':
                            hlsurl = host + rowData
                        else:
                            hlsurl = rootUrlPath + rowData
                    print(hlsurl)
                    return self.parserM3u8(hlsurl)
            print("\t{0}响应未寻找到m3u8！".format(response.text))
            return None,host,rootUrlPath
        else:
            return m3u8Info,host,rootUrlPath
            
    def getTsInfo(self,m3u8Info,host,rootpath):
        fileList = []
        allduration = 0
        if m3u8Info == None:
            return None
        index = 0
        for ts in m3u8Info.segments:
            tsurl = ts.uri
            if tsurl.find('://') < 0:
                if tsurl[0] == '/':
                    tsurl = host + tsurl
                else:
                    tsurl = rootpath + tsurl
            allduration = allduration + ts.duration
            fileList.append({'index':index,'duration':ts.duration,'url':tsurl,'downstate':0})
            index = index + 1
        tsinfo = {'alldutation':allduration,'tsfiles':fileList}
        return tsinfo

    def getKey(self,keyUrl):
        tryCount = self.tryCount
        while True:
            if tryCount < 0:
                print("\t{0}下载失败！".format(keyUrl))
                return None
            tryCount = tryCount - 1
            try:
                response = requests.get(keyUrl, timeout=20, allow_redirects=True, verify=False)
                print(response.text)
                if response.status_code == 301:
                    nowKeyUrl = response.headers["location"]
                    print("\t{0}重定向至{1}！".format(keyUrl, nowKeyUrl))
                    keyUrl = nowKeyUrl
                    continue
                expected_length = int(response.headers.get('Content-Length'))
                actual_length = len(response.content)
                if expected_length > actual_length:
                    raise Exception("key下载不完整")
                print("\t{0}下载成功！key = {1}".format(keyUrl, response.content.decode("utf-8")))
                return response.text
                break
            except :
                print("\t{0}下载失败！".format(keyUrl))
        return None
        

    def loadKey(self,m3u8Info,host,rootpath):
        if m3u8Info.keys == None:
            return None
        if len(m3u8Info.keys) == 0:
            return None
        if m3u8Info.keys[0] == None:
            return None

        # 默认选择第一个key，且AES-128算法
        key = m3u8Info.keys[0]
        if key.method != "AES-128":
            print("\t{0}不支持的解密方式！".format(key.method))
            return None
        # 如果key的url是相对路径，加上m3u8Url的路径
        keyUrl = key.uri
        if not keyUrl.startswith("http"):
            if keyUrl[0] == '/':
                keyUrl = host + keyUrl
            else:
                keyUrl = rootpath + keyUrl
        print("\t2、开始下载key...")
        self.keyText = self.getKey(keyUrl)
        self.keyVI = key.iv
        if self.keyText is None:
            return None
        print(self.keyText)
        # 判断是否有偏移量
        if key.iv is not None:
            cryptor = pyaes.AESModeOfOperationCBC(bytes(self.keyText, encoding='utf8'), bytes(key.iv, encoding='utf8'))
            #AES.new(bytes(keyText, encoding='utf8'), AES.MODE_CBC, bytes(key.iv, encoding='utf8'))
        else:
            cryptor = pyaes.AESModeOfOperationCBC(bytes(self.keyText, encoding='utf8'))
            #AES.new(bytes(keyText, encoding='utf8'), AES.MODE_CBC, bytes(keyText, encoding='utf8'))
        return cryptor
