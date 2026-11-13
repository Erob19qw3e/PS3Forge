"""Windows desktop shell and local inspection bridge for PS3 Forge."""
import os,sys,json,base64,threading,uuid,queue,traceback,time
from pathlib import Path
from urllib.parse import urlparse,parse_qs

BUNDLE=Path(__file__).resolve().parent
if getattr(sys,'frozen',False):
    candidate=Path(sys.executable).resolve().parents[2]
    HOME=candidate if (candidate/'data/projects').exists() else Path(os.environ['LOCALAPPDATA'])/'PS3Forge'
else:HOME=BUNDLE
HOME=Path(os.environ.get('PS3FORGE_HOME',str(HOME))).resolve();HOME.mkdir(parents=True,exist_ok=True)
os.environ['PS3FORGE_HOME']=str(HOME)
os.environ['QTWEBENGINE_CHROMIUM_FLAGS']=os.environ.get('QTWEBENGINE_CHROMIUM_FLAGS','')+' --force-renderer-accessibility'
import server
from http.server import ThreadingHTTPServer
from PySide6.QtCore import Qt,QUrl,QTimer,QByteArray
from PySide6.QtGui import QAction,QKeySequence,QIcon,QColor,QDesktopServices
from PySide6.QtWidgets import QApplication,QMainWindow,QMessageBox,QFileDialog
from PySide6.QtWebEngineCore import QWebEnginePage,QWebEngineProfile,QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

PORT=int(os.environ.get('PS3FORGE_PORT','8782'))
if not 1024<=PORT<=65535:raise ValueError('Invalid local editor port')
REQUESTS=queue.Queue();RESULTS={};LIVE={'ready':False};DIAG=HOME/'diagnostics';DIAG.mkdir(exist_ok=True)

def request_action(kind,payload=None):
    if len([r for r in RESULTS.values() if r['status']=='pending'])>=8:raise ValueError('Too many pending requests')
    jid=uuid.uuid4().hex[:12];RESULTS[jid]={'id':jid,'status':'pending'};REQUESTS.put((jid,kind,payload or {}))
    if len(RESULTS)>80:
        for k in list(RESULTS)[:40]:
            if RESULTS[k]['status']!='pending':RESULTS.pop(k,None)
    return {'id':jid,'status':'pending'}

class Handler(server.Handler):
    def do_GET(self):
        path=urlparse(self.path).path
        if not path.startswith('/api/desktop/'):return super().do_GET()
        try:
            self.local_host();params=parse_qs(urlparse(self.path).query)
            if path=='/api/desktop/state':return self.reply(LIVE)
            if path=='/api/desktop/health':return self.reply({'app':'PS3ForgeDesktop','version':'0.9.8','port':PORT,'pid':os.getpid(),'executable':sys.executable,'home':str(HOME),'resources':str(BUNDLE)})
            if path=='/api/desktop/job':return self.reply(RESULTS[params['id'][0]])
            if path=='/api/desktop/runtime':
                jid=LIVE.get('lastBuild');meta={}
                if jid and server.PID.fullmatch(jid):
                    f=server.BUILDS/jid/'result.json'
                    if f.exists():meta=json.loads(f.read_text(encoding='utf8'))
                appid=meta.get('appid','');log='';error=None
                if appid:
                    try:log=(HOME/'rpcs3-profile/dev_hdd0/game'/appid/'USRDIR/forge.log').read_text(encoding='utf8')[-30000:]
                    except OSError as e:error=str(e)
                folder=HOME/'rpcs3-profile/screenshots'/appid
                screenshots=sorted(folder.glob('*.png'),key=lambda f:f.stat().st_mtime,reverse=True)[:10] if appid else []
                return self.reply({'build':jid,'metadata':meta,'log':log,'logError':error,'screenshots':[{'path':str(f),'modified':f.stat().st_mtime} for f in screenshots],'note':'Screenshots are existing RPCS3 captures, not a live stream; preview images do not prove runtime behavior.'})
            if path=='/api/desktop/latest':
                p=DIAG/'latest.json';return self.reply(json.loads(p.read_text(encoding='utf8')) if p.exists() else {})
            raise ValueError('Resource is unavailable')
        except Exception as e:return self.reply({'error':str(e)},400)
    def do_POST(self):
        path=urlparse(self.path).path
        if not path.startswith('/api/desktop/'):return super().do_POST()
        try:
            self.local_host()
            if self.headers.get('X-Forge-Token')!=server.TOKEN:raise ValueError('Local token is missing')
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=100000:raise ValueError('Invalid request')
            d=json.loads(self.rfile.read(n))
            if path=='/api/desktop/capture':return self.reply(request_action('capture'))
            if path=='/api/desktop/open-project':
                if not server.PID.fullmatch(str(d.get('id',''))):raise ValueError('Invalid ID')
                return self.reply(request_action('open-project',d))
            if path=='/api/desktop/select':
                if not server.PID.fullmatch(str(d.get('id',''))):raise ValueError('Invalid ID')
                return self.reply(request_action('select',d))
            if path=='/api/desktop/command':
                if d.get('command') not in ('save','scene','game','assets','scripts','console'):raise ValueError('Command is unavailable')
                return self.reply(request_action('command',d))
            raise ValueError('Operation is unavailable')
        except Exception as e:return self.reply({'error':str(e)},400)

class Page(QWebEnginePage):
    def javaScriptConsoleMessage(self,level,message,line,source):
        with (DIAG/'web-console.log').open('a',encoding='utf8') as f:f.write(f'{level}: {source}:{line} {message}\n')
    def acceptNavigationRequest(self,url,kind,isMainFrame):
        if url.host()=='127.0.0.1' and url.port()==PORT:return True
        if url.scheme() in ('about','data','blob'):return True
        return False

class Window(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('PS3 Forge');self.resize(1440,920);self.setMinimumSize(1000,650);self.allowClose=False;self.checkingClose=False;self.polling=False
        self.setWindowIcon(QIcon(str(BUNDLE/'runtime/ICON0.PNG')))
        self.profile=QWebEngineProfile('PS3Forge-'+str(PORT),self)
        self.profile.setPersistentStoragePath(str(HOME/'data/editor-browser'/str(PORT)))
        self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache);self.profile.downloadRequested.connect(self.download)
        self.view=QWebEngineView(self);self.view.setAccessibleName('PS3 Forge editor');self.page=Page(self.profile,self.view);self.view.setPage(self.page);self.page.setBackgroundColor(QColor('#303030'));self.setCentralWidget(self.view)
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled,True)
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,False)
        self.menuBar().setNativeMenuBar(False)
        for name,actions in [
          ('File',[('Projects','home',''),('New project','newProject',''),('Save project','save','Ctrl+S'),('Import package…','importPackage',''),('Export selected package…','exportPackage',''),('Export scene package…','exportScenePackage',''),('Export project ZIP','exportProject',''),None,('Settings','settings',''),('Project folder','folder',''),('Exit','quit','Alt+F4')]),
          ('Edit',[('Undo','undo','Ctrl+Z'),('Redo','redo','Ctrl+Shift+Z'),('Duplicate object','duplicate','Ctrl+D')]),
          ('Object',[('Cube','addCube',''),('Import model…','importModel',''),('New scene','addScene',''),('New C++ script','newScript','')]),
          ('View',[('Scene','scene',''),('Game (preview)','game',''),('Assets','assets',''),('Script','scripts',''),('Console','console','')]),
          ('PS3',[('Build project','build','F7'),('Run latest build in RPCS3','rpcs3','F6')]),
          ('Tools',[('Capture for Codex','capture','F9'),('Capture folder','captures',''),('Help','help','F1')])]:
            menu=self.menuBar().addMenu(name)
            for item in actions:
                if item is None:menu.addSeparator();continue
                label,cmd,key=item;action=QAction(label,self)
                if key:action.setShortcut(QKeySequence(key))
                action.triggered.connect(lambda checked=False,c=cmd:self.command(c));menu.addAction(action)
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(250)
        project='&project='+sys.argv[sys.argv.index('--project')+1] if '--project' in sys.argv else ''
        self.view.load(QUrl(f'http://127.0.0.1:{PORT}/?desktop=1'+project))
    def command(self,name):
        if name=='quit':return self.close()
        if name in ('folder','captures'):
            return QDesktopServices.openUrl(QUrl.fromLocalFile(str(server.PROJECTS if name=='folder' else DIAG)))
        if name=='help':return QDesktopServices.openUrl(QUrl.fromLocalFile(str(BUNDLE/'HELP.md')))
        if name=='capture':request_action('capture');return
        self.page.runJavaScript('window.ForgeDesktop && window.ForgeDesktop.command('+json.dumps(name)+')')
    def download(self,item):
        file,_=QFileDialog.getSaveFileName(self,'Save file',str(HOME/'outputs'/item.suggestedFileName()))
        if not file:item.cancel();return
        p=Path(file);item.setDownloadDirectory(str(p.parent));item.setDownloadFileName(p.name);item.accept()
    def tick(self):
        if not self.polling:
            self.polling=True;self.page.runJavaScript('JSON.stringify(window.ForgeDesktop ? window.ForgeDesktop.state() : null)',self.update_state)
        if REQUESTS.empty():return
        jid,kind,d=REQUESTS.get()
        if kind=='capture':self.capture(jid)
        elif kind=='open-project':
            self.page.runJavaScript('window.ForgeDesktop.openProject('+json.dumps(d['id'])+')')
            QTimer.singleShot(1500,lambda j=jid:self.page.runJavaScript('JSON.stringify(window.ForgeDesktop.state())',lambda v:self.finish(j,v)))
        elif kind=='select':self.page.runJavaScript('JSON.stringify(window.ForgeDesktop.select('+json.dumps(d['id'])+'))',lambda value,j=jid:self.finish(j,value))
        else:
            cmd=d['command'];self.command(cmd);QTimer.singleShot(150,lambda j=jid:self.page.runJavaScript('JSON.stringify(window.ForgeDesktop.state())',lambda v:self.finish(j,v)))
    def update_state(self,value):
        self.polling=False
        try:
            data=json.loads(value) if value else None
            if not data:return
            LIVE.clear();LIVE.update({'ready':True,**data})
            title='Projects' if data.get('view')=='home' else (data.get('project') or {}).get('title','PS3 Forge');self.setWindowTitle(title+(' *' if data.get('dirty') else '')+' — PS3 Forge')
            # A readable cache for tools that do not control native windows.
            server.atomic(DIAG/'live.json',LIVE)
        except Exception as e:
            LIVE['bridgeError']=str(e)
    def finish(self,jid,value):
        try:
            result=json.loads(value) if value else None
            if not result:raise ValueError('Editor is not ready yet')
            RESULTS[jid].update(status='done',result=result)
        except Exception as e:RESULTS[jid].update(status='error',error=str(e))
    def capture(self,jid):
        self.page.runJavaScript('JSON.stringify(window.ForgeDesktop ? window.ForgeDesktop.capture() : null)',lambda v:self.save_capture(jid,v))
    def save_capture(self,jid,value):
        try:
            data=json.loads(value) if value else None
            if not data:raise ValueError('Wait for the project to finish loading')
            folder=DIAG/(time.strftime('%Y%m%d-%H%M%S')+'-'+jid);folder.mkdir()
            if not self.grab().save(str(folder/'editor.png')):raise ValueError('Window capture failed')
            for name,key in [('scene.png','scene'),('game-preview.png','gamePreview')]:
                if data['state'].get('view')=='home':continue
                raw=data[key]
                if not raw.startswith('data:image/png;base64,'):raise ValueError('Invalid 3D capture')
                (folder/name).write_bytes(base64.b64decode(raw.split(',',1)[1]))
            server.atomic(folder/'state.json',data['state'])
            result={'folder':str(folder),'editor':str(folder/'editor.png'),'scene':str(folder/'scene.png') if (folder/'scene.png').exists() else None,'gamePreview':str(folder/'game-preview.png') if (folder/'game-preview.png').exists() else None,'state':str(folder/'state.json'),'previewOnly':True}
            server.atomic(DIAG/'latest.json',result);RESULTS[jid].update(status='done',result=result)
            self.statusBar().showMessage('Capture saved: '+str(folder),8000)
        except Exception as e:RESULTS[jid].update(status='error',error=str(e))
    def closeEvent(self,event):
        if self.allowClose:event.accept();return
        event.ignore()
        if self.checkingClose:return
        self.checkingClose=True
        def checked(value):
            self.checkingClose=False
            try:d=json.loads(value) if value else {}
            except Exception:d={}
            if d.get('busy') or any(j['status']=='running' for j in server.JOBS.values()):
                QMessageBox.information(self,'Operation in progress','Wait for the build or import to finish before closing.');return
            if d.get('dirty') or d.get('scriptDirty'):
                answer=QMessageBox.question(self,'Unsaved changes','Close without saving? Choose No and use Save to keep your changes.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
                if answer!=QMessageBox.StandardButton.Yes:return
            self.allowClose=True;self.close()
        self.page.runJavaScript('JSON.stringify(window.ForgeDesktop ? window.ForgeDesktop.state() : {})',checked)

def main():
    app=QApplication(sys.argv);app.setApplicationName('PS3 Forge');app.setOrganizationName('PS3Forge');app.setStyle('Fusion')
    app.setStyleSheet('QMainWindow{background:#303030} QMenuBar{background:#292929;color:#d0d0d0;font:11px "Segoe UI";padding:1px} QMenuBar::item:selected{background:#454545} QMenu{background:#353535;color:#ddd;border:1px solid #222} QMenu::item{padding:5px 25px} QMenu::item:selected{background:#455e72} QStatusBar{background:#303030;color:#aaa;font:10px "Segoe UI"}')
    try:http=ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
    except OSError:
        QMessageBox.information(None,'PS3 Forge',f'PS3 Forge Desktop is already open, or local port {PORT} is in use.');return 1
    threading.Thread(target=http.serve_forever,daemon=True).start()
    w=Window();w.show();result=app.exec();http.shutdown();return result
if __name__=='__main__':
    try:sys.exit(main())
    except Exception:
        (HOME/'desktop-error.log').write_text(traceback.format_exc(),encoding='utf8');raise
