import StellarPlayer
import json
import urllib
import os
import re
import time
import threading
from .hlsDownloader import hlsDownloader

class m3u8Downloadplugin(StellarPlayer.IStellarPlayerPlugin):
    def __init__(self,player:StellarPlayer.IStellarPlayer):
        super().__init__(player)
        self.hlslist = []
        self.downlist = []
        self.savepath = self.player.dataDirectory + os.path.sep
        self.runing = True
        self.timethread = None
        
    def reflashDownInfo(self):
        self.hlslist = []
        for item in self.downlist:
            xzzt = ''
            if item.downstate == 0:
                xzzt = '未开始'
            if item.downstate == -1:
                xzzt = '已暂停'
            if item.downstate == 1:
                xzzt = '下载中'
            if item.downstate == 2:
                xzzt = '已下载'
            newinfo = {'hlsname':item.medianame,'hlsdowned':item.downpercent,'successed':item.downedsuccess,'hlsstates':xzzt,'delete':'删除','play':'播放'}
            self.hlslist.append(newinfo)
        
    def timer(self):
        while self.runing:
            self.reflashDownInfo()
            self.player.updateControlValue('main', 'hlsgrid', self.hlslist)
            time.sleep(1)
        
    def show(self):
        controls = self.makeLayout()
        self.doModal('main',800,600,'',controls)
    
    def start(self):
        super().start()
        print('----------')
        print(self.savepath)
        for root, dirs, files in os.walk(self.savepath): 
            for file in files:
                filenames = os.path.splitext(file)
                print(file)
                fileisjson = (len(re.findall(r"(.+?).json", file)) > 0)
                if os.path.splitext(file)[1] == '.json':
                    self.loaddownjson(self.savepath + os.path.sep + file)
        self.runing = True
        self.timethread = threading.Thread(target=self.timer)
        self.timethread.start()
        
    def loaddownjson(self,jsonfile):
        newdown = hlsDownloader()
        newdown.loadInfoFromJson(jsonfile)
        newdown.downToFile(newdown.savePath)
        self.downlist.append(newdown)
        
    def newdown(self,name,url):
        newdown = hlsDownloader()
        newdown.setmedianame(name)
        newdown.openM3u8Url(url)
        if newdown.TsInfo == None:
            self.player.toast('addhls', 'm3u8地址打开失败')
            return
        path = self.savepath + name +'.ts'
        newdown.downToFile(path)
        self.downlist.append(newdown)
        
    def stop(self):
        for item in self.downlist:
            item.saveInfoToJson()
        self.runing = False
        if self.timethread != None:
            self.timethread.join()
        return super().stop()
        
    def getPlayerM3u8(self):
        playinfo = self.player.getPlayInfo()
        if playinfo:
            if playinfo['status'] == 0:
                if 'url' in playinfo:
                    return playinfo['url']
        return None
        
    def makeLayout(self):
        hldesc = [
            {'type':'label','name':'名称','width':0.5},
            {'type':'label','name':'已下载','width':0.1},
            {'type':'label','name':'完好率','width':0.1},
            {'type':'label','name':'状态','width':0.1},
            {'type':'space','width':0.2}
        ]
        hlsgrid_layout = [
            {
                'group':[
                    {'type':'label','name':'hlsname','width':0.5},
                    {'type':'label','name':'hlsdowned','width':0.1},
                    {'type':'label','name':'successed','width':0.1},
                    {'type':'link','name':'hlsstates','width':0.1,'@click':'onStateClick'},
                    {'type':'link','name':'delete','width':0.1,'@click':'onDelClick'},
                    {'type':'link','name':'play','width':0.1,'@click':'onPlayClick'}
                ]
            }
        ]
        controls = [
            {'group':hldesc,'height':30},
            {'type':'space','height':5},
            {'type':'list','name':'hlsgrid','itemlayout':hlsgrid_layout,'value':self.hlslist,'separator':True,'itemheight':40},
            {'type':'space','height':5},
            {
                'group':[
                    {'type':'button','name':'新增下载','@click':'onAddDownload'},
                    {'type':'space','width':5},
                    {'type':'button','name':'打开下载目录','@click':'onOpenDir'},
                    {'type':'space','width':0.7},
                ],
                'height':30
            },
            {'type':'space','height':5}
        ]
        return controls
    
    def onStateClick(self, page, listControl, item, itemControl):
        hlsdown = self.downlist[item]
        print(hlsdown.downstate)
        if hlsdown.downstate == 0:
            hlsdown.downToFile(hlsdown.savePath)
            return
        if hlsdown.downstate == 1:
            hlsdown.stop()
            return
        if hlsdown.downstate == -1:
            hlsdown.downToFile(hlsdown.savePath)
            return
        if hlsdown.downstate == 2:
            self.player.toast('main', '文件已下载完成')
    
    def onDelClick(self, page, listControl, item, itemControl):
        hlsdown = self.downlist[item]
        tsfile = hlsdown.medianame + '.ts'
        jsonfile = hlsdown.medianame + '.json'
        print(tsfile)
        print(jsonfile)
        hlsdown.stop()
        self.downlist.remove(hlsdown)
        self.reflashDownInfo()
        del hlsdown
        self.player.updateControlValue('main', 'hlsgrid', self.hlslist)
        os.remove(tsfile)
        os.remove(jsonfile)
    
    def onPlayClick(self, page, listControl, item, itemControl):
        hlsdown = self.downlist[item]
        tsfile = hlsdown.savePath
        name = hlsdown.medianame
        self.player.play(tsfile,name)
    
    def onAddDownload(self,*args):
        controls = [
            {'type': 'space', 'height': 10},
            {'type': 'edit', 'name':'hlsurl','label': 'm3u8地址', 'height': 30},
            {'type': 'space', 'height': 10},
            {'type': 'edit', 'name':'downname','label': '下载名称', 'height': 30},
            {'type': 'space', 'height': 10},
            {
                'group':[
                    {'type': 'space', 'width': 400},
                    {'type': 'button','name':'开始下载','@click':'onAddHlsDown'},
                    {'type': 'space', 'width': 10},
                    {'type': 'button','name':'当前地址','@click':'onGetActHlsAdd'},
                ],
                'height':40
            }
        ]
        self.doModal('addhls',600,140,'',controls)
        
    def onOpenDir(self,*args):
        os.startfile(self.savepath)
        
    def onAddHlsDown(self,*args):
        name = self.player.getControlValue('addhls', 'downname')
        downurl = self.player.getControlValue('addhls', 'hlsurl')
        name = name.strip()
        downurl = downurl.strip()
        if name == '' :
            self.player.toast('addhls', '下载名称不能为空')
            return
        if downurl == '':
            self.player.toast('addhls', 'm3u8地址不能为空')
            return
        if downurl.find('.m3u8') < 0 or downurl.find('http') < 0:
            self.player.toast('addhls', '视频地址非m3u8地址')
            return
        for item in self.downlist:
            if item.medianame == name:
                self.player.toast('addhls', '下载名称已存在')
                return
        self.newdown(name,downurl)
        self.player.closeModal('addhls',True)
    
    def onGetActHlsAdd(self,*args):
        playerhls = self.getPlayerM3u8()
        if playerhls == None:
            self.player.toast('addhls', '未能取得当前视频地址')
            return
        if playerhls.find('.m3u8') < 0 and playerhls.find('http') < 0:
            self.player.toast('addhls', '当前视频非m3u8地址')
            return
        self.player.updateControlValue('addhls', 'hlsurl', playerhls)
    
def newPlugin(player:StellarPlayer.IStellarPlayer,*arg):
    plugin = m3u8Downloadplugin(player)
    return plugin

def destroyPlugin(plugin:StellarPlayer.IStellarPlayerPlugin):
    plugin.stop()