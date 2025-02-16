import os
import json
import sys
import threading
import subprocess

def IsModulePresent(module) -> bool:
    result = True
    try:
        import module
    except ModuleNotFoundError:
        result = False
    finally:
        return result

def ModuleChecker(autoInstall: bool, modules : dict):
    for name, m in modules:
        if not IsModulePresent(m):
            print("Module " + name + " is not present on system")
            if autoInstall:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', name], stdout=subprocess.DEVNULL)

def CheckBaseModules(autoInstall: bool):
    modules_map = {
        "enum":             enum,
        "python-ffmpeg":    ffmpeg,
        "multiprocessing":  multiprocessing
    }
    ModuleChecker(autoInstall, modules_map)

if (len(sys.argv)) > 2 and ('-module_check' in sys.argv or "--mc" in sys.argv):
    CheckBaseModules(True)

import re
import shutil
import multiprocessing
import queue
import enum
import ffmpeg

g_out_format  = ".m4a"
g_working_dir = "out"

class DefaultMetaInfo:
    AlbumName    = None
    AuthorName   = None
    CoverPath    = None
    Year         = None
class FileMetainfo(DefaultMetaInfo):
    ExplicitCoverPath = None
    ExplicitPath      = None
    TrackName         = None
    TrackId           = -1
    FileName          = ""

g_album_info = list()

class Tasks(enum.IntFlag):
    none        = 0,
    Convert     = 1,
    Cover       = 2,
    Tags        = 4,
    CopyLyrics  = 8,
    All         = 7

class Worker(threading.Thread):
    def __init__(self, tasks):
        threading.Thread.__init__(self)
        self.tasks = tasks
        self.daemon = True
        self.start()

    def run(self):
        while True:
            func, args, kargs = self.tasks.get()
            try:
                func(*args, **kargs)
            except Exception as e:
                print(e)
            finally:
                self.tasks.task_done()

class ThreadPool:
    def __init__(self, num_threads):
        self.tasks = queue.Queue(num_threads)
        for i in range(num_threads):
            Worker(self.tasks)

    def add_task(self, func, *args, **kargs):   
        self.tasks.put((func, args, kargs))

    def wait_completion(self):
        self.tasks.join()

def async_task_await(task, cmd):
    os.system(task + cmd)
    process = subprocess.Popen([task, cmd], None, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process.wait()

def ExtractCover(filename : str, out : str | None):
    if out == None:
        out = "cover.jpg"
    current_dir = os.getcwd()
    stream = ffmpeg.input(current_dir + "\\" + filename)
    stream = ffmpeg.output(stream, out, **{"frames:v": "1"})
    try:
        ffmpeg.run(stream)
    except:
        return False
    return True

def prepare_meta(schema):
    cover_extraction_required = False
    file = open(schema, "rb")
    album_meta = json.load(file)
    for rec in album_meta:
        if (rec == "default"):
            #parse Default data
            default_data = FileMetainfo()
            for sub_rec in album_meta[rec]:
                if (sub_rec.lower() == "author"):
                    default_data.AuthorName = album_meta[rec][sub_rec]
                    continue
                if (sub_rec.lower() == "album"):
                    default_data.AlbumName = album_meta[rec][sub_rec]
                    continue
                if (sub_rec.lower() == "cover"):
                    default_data.CoverPath = album_meta[rec][sub_rec]
                    if (type(default_data.CoverPath) == int):
                        cover_extraction_required = True
                    continue
                if (sub_rec == "Year" and album_meta[rec][sub_rec] != ''):
                    default_data.Year = int(album_meta[rec][sub_rec])
                    continue
            g_album_info.append(default_data)
        else:
            record = FileMetainfo()
            if len(rec) > 0:
                record.TrackId = int(rec)
            else:
                record.TrackId = ''
            for sub_rec in album_meta[rec]:
                if (type(sub_rec) == str):
                    record.TrackName = sub_rec
                if (type(sub_rec) == dict):
                    #supported cover, file
                    key = list(sub_rec.keys())[0]
                    if (str(key).lower() == "author"):
                        record.AuthorName = sub_rec[key]
                    if (str(key).lower() == "cover"):
                        record.ExplicitCoverPath = sub_rec[key]
                    if (str(key).lower() == "file"):
                        record.ExplicitPath = sub_rec[key]
                if record.ExplicitPath != None:
                    record.FileName = g_album_info[0].AuthorName + ' - ' + record.ExplicitPath
                else:
                    record.FileName = g_album_info[0].AuthorName + ' - ' + record.TrackName
            g_album_info.append(record)
    if cover_extraction_required:
        ExtractCover(g_album_info[default_data.CoverPath].FileName)
        g_album_info[0].CoverPath = "cover.jpg"

    return len(g_album_info) > 1

def add_tags(songId : int):
    current_dir = os.getcwd() + '\\' + g_working_dir
    files_list = [f for f in os.listdir(current_dir)
        if os.path.isfile(os.path.join(current_dir,f))]
    it = g_album_info[songId]
    src_path = current_dir + '\\' + it.FileName + g_out_format
    tmp_path = current_dir + '\\' + "tmp_" + it.FileName + g_out_format
    author_string = g_album_info[0].AuthorName
    if type(it.AuthorName) is str and g_album_info[0].AuthorName not in it.AuthorName:
        author_string += ', ' + it.AuthorName
    year_str = ""
    if it.Year is not None:
        year_str = it.Year
    else:
        year_str = str(g_album_info[0].Year)
    stream = ffmpeg.input(src_path)
    stream = ffmpeg.output(stream, tmp_path,
    metadata= ['artist=' + author_string,
                'album=' + g_album_info[0].AlbumName,
                'date='  + year_str,
                'track=' + str(it.TrackId),
                'title=' + it.TrackName ],
    **{'c:0': 'copy'})
    ffmpeg.run(stream)
    os.system("del " + '\"' + src_path + '\"')
    os.system("move " + '\"' + tmp_path + '\" \"' + src_path+ '\"')
    return True

def add_cover(songId : int):
    current_dir = os.getcwd()
    files_list = [f for f in os.listdir(current_dir + '\\' + g_working_dir)
        if os.path.isfile(os.path.join(current_dir + '\\' + g_working_dir,f))]
    it = g_album_info[songId]
    cover_path = None
    if (it.ExplicitCoverPath):
        cover_path = it.ExplicitCoverPath         
    else:
        cover_path = g_album_info[0].CoverPath
    if (os.access(g_working_dir + '\\' + cover_path, os.O_RDONLY) == False):
        shutil.copy(cover_path, g_working_dir + '\\' + cover_path)
    src_path = current_dir + '\\' + g_working_dir + '\\' + it.FileName + g_out_format
    tmp_path = current_dir + '\\' + g_working_dir + '\\' + "tmp_" + it.FileName + g_out_format
    audio_stream = ffmpeg.input(src_path).audio
    cover_stream = ffmpeg.input(current_dir + '\\' + g_working_dir + '\\' + cover_path)
    audio_stream = ffmpeg.output(audio_stream, cover_stream, tmp_path, acodec='copy', 
                                    **{'c': 'copy', "disposition:1":'attached_pic'})
    ffmpeg.run(audio_stream)
    os.system("del " + '\"' + src_path + '\"')
    os.system("move " + '\"' + tmp_path + '\" \"' + src_path+ '\"')
    return True

def mp3_convert(songId : int):
    current_dir = os.getcwd()
    files_list = [f for f in os.listdir(current_dir) if os.path.isfile(os.path.join(current_dir,f))]
    it = g_album_info[songId]
    track_name = None
    if (it.ExplicitPath != None):
        track_name = it.ExplicitPath
    else:
        track_name = it.TrackName
    res = False
    pattern = re.compile(track_name.replace('(',"\\(").replace(')',"\\)").replace('[',"\\[").replace(']',"\\]"), re.I)
    for i in files_list:
        match = pattern.search(i)
        if (match):
            audio_stream = ffmpeg.input(current_dir + "\\" + match.string).audio
            audio_stream = ffmpeg.output(audio_stream, current_dir + "\\" + g_working_dir
                 + "\\" + g_album_info[0].AuthorName + ' - ' + track_name + g_out_format, acodec='aac')
            ffmpeg.run(audio_stream)
            return True
    return False

def Executable(cmdFlags: Tasks, songId : int):
    if (cmdFlags & Tasks.Convert):
        if (not mp3_convert(songId)):
            print("Unable to find file from json scheme")
            return       
    if (cmdFlags & Tasks.Cover):
        if (not add_cover(songId)):
            print("Failed to add cover")
            return
    if (cmdFlags & Tasks.CopyLyrics):
        if (not copy_lyrics(songId)):
            print("Unable copy lyrics from source file")
            return       
    if (cmdFlags & Tasks.Tags):
        if (not add_tags(songId)):
            print("Failed to add track data")
            return

def converter(args : list):
    convert_task = Tasks.All
    if (len(args) > 1):
        skip_next = False
        for i in range(len(args)):
            if (skip_next):
                skip_next = False
                continue
            if (args[i] == "--lyrics"):
                convert_task = convert_task | Tasks.CopyLyrics
            if (args[i] == "--skip"):
                if (args[i+1].lower() == "convert" and (convert_task & Tasks.Convert)):
                    convert_task = convert_task ^ Tasks.Convert
                if (args[i+1].lower() == "cover" and (convert_task & Tasks.Cover)):
                    convert_task = convert_task ^ Tasks.Cover
                if (args[i+1].lower() == "tags" and (convert_task & Tasks.Tags)):
                    convert_task = convert_task ^ Tasks.Tags

    if (not prepare_meta("format.json")):
        print("Convert file isn't a json file")
        return

    current_dir = os.getcwd()
    if (not os.path.exists(current_dir + "\\" + g_working_dir)):
        os.mkdir(current_dir + "\\" + g_working_dir)
    pool = ThreadPool(multiprocessing.cpu_count())
    for i in range(len(g_album_info) - 1):
        pool.add_task(Executable, convert_task, i + 1)
    pool.wait_completion()
    print("Task complete!")

def CheckParserModules(autoInstall: bool):
    modules_map = {
        "functools":            functools,
        "PyQt5":                PyQt5.QtCore,
        "PyQtWebEngine-Qt5":    PyQt5.QtWebEngineWidgets
    }
    ModuleChecker(autoInstall, modules_map)

if (len(sys.argv)) > 2 and ('-module_check' in sys.argv or "--mc" in sys.argv):
    CheckParserModules(True)

import functools
import PyQt5.QtCore
import PyQt5.QtWidgets
import PyQt5.QtWebEngineWidgets

class QtRendererWarp(PyQt5.QtWidgets.QWidget, PyQt5.QtWebEngineWidgets.QWebEnginePage):

    @PyQt5.QtCore.pyqtSlot()
    def HtmlReciever(self, data : str | None):
        self.html = data

    @PyQt5.QtCore.pyqtSlot()
    def OnLoadFinished(self, ok : bool):
        self.enough = ok
        
    def __init__(self, url):
        self.html = None
        self.app = PyQt5.QtWidgets.QApplication(sys.argv)       
        self.browser = PyQt5.QtWebEngineWidgets.QWebEngineView()
        self.browser.load(PyQt5.QtCore.QUrl(url))
        self.browser.loadFinished.connect(functools.partial(self.OnLoadFinished))
        self.page = self.browser.page()
        self.enough = False
        while self.enough == False:
            self.app.processEvents(PyQt5.QtCore.QEventLoop.WaitForMoreEvents)
        self.browser.page().toHtml(functools.partial(self.HtmlReciever))
        while self.html == None:
            self.app.processEvents(PyQt5.QtCore.QEventLoop.WaitForMoreEvents)

def CheckDownloaderModules(autoInstall: bool):
    CheckParserModules(autoInstall)
    modules_map = {
        "bs4":       bs4,
        "pytubefix": pytubefix,
        "requests":  requests
    }
    ModuleChecker(autoInstall, modules_map)

if (len(sys.argv)) > 2 and ('-module_check' in sys.argv or "--mc" in sys.argv):
    CheckDownloaderModules(True)

import bs4
import pytubefix
import requests

def parse_ytb_album(page : bs4.BeautifulSoup) -> tuple[list, dict]:
    playlist_links = dict()
    default_data_list = dict()
    regex = r"[\x00-\x20]"
    album_data_list = list(page.find("ytmusic-responsive-header-renderer").findAll("yt-formatted-string"))
    playlist_data = page.find("ytmusic-shelf-renderer").findAll("yt-formatted-string")
    playlist_data_list = list()
    step_count = 2
    for i in playlist_data:
        if "index" in i.attrs['class'] or "title" in i.attrs['class']:
            playlist_data_list.append(i)
        elif "complex-string" in i.attrs['class']:
            playlist_data_list.append(i)
            step_count = 3
    default_data_list.update({"Author" : album_data_list[0].text})
    default_data_list.update({"Album" : album_data_list[1].text})
    default_data_list.update({"Year" : album_data_list[2].text}) # Fix with hands C:
    default_data_list.update({"cover" : "cover.jpg"})
    result = {"default" : default_data_list}
    cover_required = True
    for i in range(0,len(playlist_data_list), step_count):
        # 0 - order
        # 1 - Track Name
        # 2 - Explicit Author (Multiple autors, feats)
        # 3 - Views (useless)
        # 4 - Duration (useless)
        # 5 - Nothing?
        order =  playlist_data_list[i].text
        name  =  playlist_data_list[i + 1].text 
        track_explicit_data = [name] # explicit: author, file, cover
        regex_frbdn_symb = r"^[ .]|[/<>:\"\\|?*]+|[ .]$"
        match = re.findall(regex_frbdn_symb, name)
        if len(match) > 0:
            track_explicit_data.append({"file" : re.sub(pattern=regex_frbdn_symb, repl='', string=name)})
        if i+2 < len(playlist_data_list) and "complex-string" in playlist_data_list[i + 2].attrs['class']:
            track_explicit_data.append({"author" : playlist_data_list[i + 2].text})
        result.update({order : track_explicit_data})
        data = dict()
        data.update({"cover_required": cover_required})
        song_link = playlist_data_list[i + 1].contents[0].attrs['href']
        pos = song_link.find("&list=")
        data.update({"link": song_link[0:pos]})
        playlist_links.update({order : data})
        cover_required = False
    return result, playlist_links

def parse_ytb_playlist(page : dict) -> tuple[list, dict]:
    playlist_links = dict()
    playlist_data = page["contents"]["twoColumnWatchNextResults"]["playlist"]["playlist"]
    default_data_list = list()
    default_data_list.append({"Author" : ""})
    default_data_list.append({"Album" : playlist_data["title"]})
    default_data_list.append({"Year" : ""}) # This is a playlist, universal answer is to add explicit param to each song...
    default_data_list.append({"cover" : "cover.jpg"})
    result = {"default" : default_data_list}
    explicit_ordering = 1
    for i in list(playlist_data["contents"]):
        order = explicit_ordering
        name = i["playlistPanelVideoRenderer"]["title"]["simpleText"]
        track_explicit_data = [name] # explicit: author, file, cover
        regex_frbdn_symb = r"^[ .]|[/<>:\"\\|?*]+|[ .]$"
        match = re.findall(regex_frbdn_symb, name)
        if len(match) > 0:
            track_explicit_data.append({"file" : re.sub(pattern=regex_frbdn_symb, repl='', string=name)})
        track_explicit_data.append({"author" : i["playlistPanelVideoRenderer"]["longBylineText"]["runs"][0]["text"]})
        track_explicit_data.append({"year" : ""})
        result.update({order : track_explicit_data})
        data_dict = dict()
        data_dict.update({"cover_required": True})
        data_dict.update({"cover_link": i["playlistPanelVideoRenderer"]["thumbnail"]["thumbnails"][-1]["url"]})
        playlist_links.update({order : [i["playlistPanelVideoRenderer"]["videoId"], data_dict]})
        explicit_ordering += 1
    return result, playlist_links

def parse_ytb_song(page: bs4.BeautifulSoup) -> tuple[list, dict]:
    playlist_links = dict()
    for s in page.select('script'):
        s.extract()
    default_data_list = dict()
    default_data_list.update({"Author" : list(page.findAll("meta", {"property" : "og:video:tag"}))[0].attrs["content"]})
    default_data_list.update({"Album" : ""})
    default_data_list.update({"Year" : ""})
    default_data_list.update({"cover" : "cover.jpg"})
    result = {"default" : default_data_list}
    result.update({'1': [list(page.findAll("title"))[0].text]})
    data =  {"cover_required": True}
    song_link = list(page.findAll("meta", {"property" : "og:url"}))[0].attrs["content"]
    pos = song_link.find("watch?v=")
    data.update({"link": song_link[pos+8:]})
    playlist_links.update({'0' : data})
    return result, playlist_links

def parse_ytb_page(page : bs4.BeautifulSoup) -> tuple[list, dict] | None:
    renderer = page.find("ytmusic-two-column-browse-results-renderer")
    if renderer is not None:
        #find sutable diffrence btw album & playlist!
        #if renderer.find("ytmusic-shelf-renderer"):
        #    return parse_ytb_playlist(renderer)
        #else:
        return parse_ytb_album(renderer)
    else:
        return parse_ytb_song(page)

def prepare_download_schemes(url: str, dump: bool):
    unique_link_offset = url.find("=")
    refind_url = ""
    if unique_link_offset == -1:
        return
    elif url.find("playlist?list") != -1:
        refind_url = "https://music.youtube.com/playlist?list" + url[unique_link_offset:]
    else:
        refind_url = "https://www.youtube.com/watch?v" + url[unique_link_offset:]
    base_html = QtRendererWarp(refind_url).html
    ytb_soup = bs4.BeautifulSoup(base_html, 'html.parser')
    scheme, playlist_data = parse_ytb_page(ytb_soup)
    if dump:
        with open("format.json", "wb") as scheme_file:
            scheme_file.write(json.dumps(scheme, ensure_ascii=False, indent=1).encode())
        with open("download_list.json", "wb") as links_file:
            links_file.write(json.dumps(playlist_data, ensure_ascii=False, indent=1).encode())
    else:
        return scheme, playlist_data

def downloader(url: str, schemesPrepared: bool, explicitSchemeName: str | None = None, explicitPlaylistName: str | None = None):
    scheme = list()
    playlist_data = dict()
    if schemesPrepared:
        if explicitSchemeName is None:
            explicitSchemeName = "format.json"
        with open(explicitSchemeName, "rb") as scheme_file:
            scheme = json.load(scheme_file)
        if explicitPlaylistName is None:
            explicitPlaylistName = "download_list.json"
        with open(explicitPlaylistName, "rb") as playlist_data:
            playlist_data = json.load(playlist_data)
    else:
        scheme, playlist_data = prepare_download_schemes(url, False)
    if scheme == None or playlist_data == None:
        return
    if not schemesPrepared:
        with open("format.json", "wb") as scheme_file:
            scheme_file.write(json.dumps(scheme, ensure_ascii=False, indent=1).encode())
    base_link = 'http://youtube.com/watch?v='
    pytubefix.helpers.reset_cache()
    output_path = os.getcwd()
    for i in playlist_data:
        track_id = playlist_data[i]["link"]
        link = None
        if track_id == None:
            link = url
        else:
            link = base_link + track_id
        vid = pytubefix.YouTube(link, 'WEB' )
        track = None
        try:
            track = vid.streams.get_audio_only()
        except:
            type, value, traceback = sys.exc_info()
            print("Missing track: " + str(i) + ", reason: " + value.args[0]) #add exception details
            continue
        finally:
            if track:
                filename = ""
                if len(scheme[i]) > 1 and "file" in scheme[i][1]:
                    filename = scheme[i][1]["file"]
                else:
                    filename = scheme[i][0]
                track.download(output_path = output_path, filename = filename + '.' + track.subtype)
                if playlist_data[i] and playlist_data[i] and playlist_data[i]["cover_required"]:
                    stream = vid.streams.get_highest_resolution(False)
                    if stream:
                        cover_vid_name = stream.default_filename
                        stream.download(output_path = output_path, filename=cover_vid_name)
                        ExtractCover(cover_vid_name, scheme["default"]["cover"])
                        os.remove(output_path + '\\' + cover_vid_name)
                    else:
                        cover_data = requests.get(playlist_data[i][0])
                        with open(scheme["default"]["cover"], 'wb') as localFile:
                            localFile.write(cover_data.content)                       
    return

class Args(enum.IntFlag):
    Empty       = 0,
    PrepareMeta = 1,
    Download    = 2,
    Convert     = 4

if __name__ == "__main__":
    if len(sys.argv) < 2:
        converter(sys.argv)
        exit(0)
    args_flags = Args.Empty;
    for it in sys.argv:
        if it == "-get_modules" or it == "--gm":
            module_check_skip = False
        if it == "-prepare_meta" or it == "--pm":
            args_flags |= Args.PrepareMeta
        elif it == "-downloader" or it == "--d":
            args_flags |= Args.Download
        elif it[0:2] == "--":
            args_flags = Args.Convert
    # i don't want to detect url link in prepare stage tbh it just went last
    if args_flags & Args.Convert:
        converter(sys.argv)
        exit(0)
    if args_flags & Args.PrepareMeta:
        prepare_download_schemes(sys.argv[len(sys.argv) - 1], True)
    if args_flags & Args.Download:
        downloader(sys.argv[len(sys.argv) - 1], args_flags & Args.PrepareMeta)