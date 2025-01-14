import os
import re
import shutil
import json
import subprocess
import threading
import multiprocessing
import queue
import sys
import enum
import ffmpeg

exif_exe      = "exiftool.exe"
g_out_format  = ".m4a"
g_working_dir = "out"

class DefaultMetaInfo:
    AlbumName    = None
    AuthorName   = None
    CoverPath    = None
    Year         = 1970

class FileMetainfo(DefaultMetaInfo):
    ExplicitCoverPath = None
    ExplicitPath      = None
    TrackName         = None
    TrackId           = -1
    FileName          = ""

g_album_info = list()

class Tasks(enum.IntFlag):
    none = 0,
    Convert = 1,
    Cover = 2,
    Tags = 4,
    CopyLyrics = 8,
    All = 7

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

def ExtractCover(songId : int):
    current_dir = os.getcwd()
    files_list = [f for f in os.listdir(current_dir) if os.path.isfile(os.path.join(current_dir,f))]
    track_name = g_album_info[songId].TrackName
    pattern = re.compile(track_name.replace('(',"\\(").replace(')',"\\)"), re.I)
    for i in files_list:
        match = pattern.search(i)
        if (match):
            stream = ffmpeg.input(current_dir + "\\" + match.string)
            stream = ffmpeg.output(stream, "cover.jpg", **{"frames:v": "1"})
            ffmpeg.run(stream)
            g_album_info[0].CoverPath = "cover.jpg"
            return True
    return False

def prepare_meta(schema):
    cover_extraction_required = False
    file = open(schema, "rb")
    album_meta = json.load(file)
    for rec in album_meta:
        if (rec == "default"):
            #parse Default data
            default_data = FileMetainfo()
            for sub_rec in album_meta[rec]:
                key = list(sub_rec.keys())[0]
                if (key == "Author"):
                    default_data.AuthorName = sub_rec[key]
                if (key == "Album"):
                    default_data.AlbumName = sub_rec[key]
                if (key == "cover"):
                    default_data.CoverPath = sub_rec[key]
                    if (type(default_data.CoverPath) == int):
                        cover_extraction_required = True
                if (key == "Year"):
                    default_data.Year = int(sub_rec[key])
            g_album_info.append(default_data)
        else:
            record = FileMetainfo()
            record.TrackId = int(rec)
            for sub_rec in album_meta[rec]:
                if (type(sub_rec) == str):
                    record.TrackName = sub_rec
                if (type(sub_rec) == dict):
                    #supported cover, file
                    key = list(sub_rec.keys())[0]
                    if (key == "cover"):
                        record.ExplicitCoverPath = sub_rec[key]
                    if (key == "file"):
                        record.ExplicitPath = sub_rec[key]
                if record.ExplicitPath != None:
                    record.FileName = record.ExplicitPath
                else:
                    record.FileName = g_album_info[0].AuthorName + ' - ' + record.TrackName
            g_album_info.append(record)
    if cover_extraction_required:
        ExtractCover(default_data.CoverPath)

    return len(g_album_info) > 1

def add_tags(songId : int):
    current_dir = os.getcwd() + '\\' + g_working_dir
    files_list = [f for f in os.listdir(current_dir) if os.path.isfile(os.path.join(current_dir,f))]
    it = g_album_info[songId]
    src_path = current_dir + '\\' + it.FileName + g_out_format
    tmp_path = current_dir + '\\' + "tmp_" + it.FileName + g_out_format
    stream = ffmpeg.input(src_path)
    stream = ffmpeg.output(stream, tmp_path,
    metadata=['artist=' + g_album_info[0].AuthorName,
                'album=' + g_album_info[0].AlbumName,
                'date=' + str(g_album_info[0].Year),
                'track=' + str(it.TrackId),
                'title=' + it.TrackName ],
    **{'c:0': 'copy'})
    ffmpeg.run(stream)
    os.system("del " + '\"' + src_path + '\"')
    os.system("move " + '\"' + tmp_path + '\" \"' + src_path+ '\"')
    return True

def add_cover(songId : int):
    current_dir = os.getcwd()
    files_list = [f for f in os.listdir(current_dir + '\\' + g_working_dir) if os.path.isfile(os.path.join(current_dir + '\\' + g_working_dir,f))]
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
    pattern = re.compile(track_name.replace('(',"\\(").replace(')',"\\)"), re.I)
    for i in files_list:
        match = pattern.search(i)
        if (match):
            audio_stream = ffmpeg.input(current_dir + "\\" + match.string).audio
            audio_stream = ffmpeg.output(audio_stream, current_dir + "\\" + g_working_dir + "\\" + g_album_info[0].AuthorName + ' - ' + track_name + g_out_format, acodec='aac')
            ffmpeg.run(audio_stream)
            return True
    return False

def copy_lyrics(songId : int):
    current_dir = os.getcwd()
    files_list = [f for f in os.listdir(current_dir + '\\' + g_working_dir) if os.path.isfile(os.path.join(current_dir + '\\' + g_working_dir,f))]
    it = g_album_info[songId]
    track_name = None
    if (it.ExplicitPath != None):
        track_name = it.ExplicitPath
    else:
        track_name = it.TrackName
    pattern = re.compile(track_name.replace('(',"\\(").replace(')',"\\)"), re.I)
    res = False
    for i in files_list:
        match = pattern.search(i)
        if (match):
            cmd = " -overwrite_original -TagsFromFile "
            cmd += '\"' + current_dir + '\\' + track_name  + match.string + '\"'
            cmd += " -Lyrics "
            cmd += '\"' + current_dir + '\\' + g_working_dir + '\\' + i + '\"'
            async_task_await(exif_exe, cmd)
            res = True
            break
    if (res == False):
        return False
    return True

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

import PyQt5.QtGui
import PyQt5.QtCore
import PyQt5.QtWebEngine
import PyQt5.QtWebEngineWidgets

class QtRendererWarp(PyQt5.QtWebEngineWidgets.QWebEnginePage):
    def __init__(self, url):  
        self.html = None
        self.app = PyQt5.QtWidgets.QApplication(sys.argv)
        PyQt5.QtWebEngineWidgets.QWebEnginePage.__init__(self)  
        self.loadFinished.connect(self._loadFinished)
        self.load(PyQt5.QtCore.QUrl(url))
        self.app.exec_() 

    def _callable(self, data):
        self.html = data

    def _loadFinished(self, result):  
        self.toHtml(self._callable)
        while self.html is None:
                self.app.processEvents(PyQt5.QtCore.QEventLoop.ExcludeUserInputEvents | PyQt5.QtCore.QEventLoop.ExcludeSocketNotifiers | PyQt5.QtCore.QEventLoop.WaitForMoreEvents)
        self.app.quit()

def format_json_sceme(content : dict, playlist : dict):
    result = list()
    default_data_list = list()
    if "title" in playlist: #Custom playlist
        default_data_list.append({"Author" : ""})
        default_data_list.append({"Album" : playlist["title"]})
    else:
        default_data_list.append({"Author" : playlist[0]["playlistVideoRenderer"]["shortBylineText"]["runs"][0]["text"]})
        default_data_list.append({"Album" : content["metadata"]["playlistMetadataRenderer"]["title"]})
    default_data_list.append({"Year" : ""})
    default_data_list.append({"cover" : "cover.jpg"})
    result = {"default" : default_data_list} 
    if "contents" in playlist:
        playlist = playlist["contents"]
    for i in list(playlist):
        order = None
        name = None
        if "playlistVideoRenderer" in i :
            order = i["playlistVideoRenderer"]["index"]["simpleText"]
            name = i["playlistVideoRenderer"]["title"]["runs"][0]["text"]
        elif "playlistPanelVideoRenderer" in i:
            order = i["playlistPanelVideoRenderer"]["indexText"]["simpleText"]
            name = i["playlistPanelVideoRenderer"]["title"]["simpleText"]
        if order and name:
            regex = r"^[ .]|[/<>:\"\\|?*]+|[ .]$"
            match = re.findall(regex, name)
            if len(match) > 0:
                explicit_file = {"file" : re.sub(pattern=regex, repl='', string=name)}
                track_list = [ name ]
                track_list.append(explicit_file)
                result.update({order : track_list})
            else:
                result.update({order : [name]})
    print("Album / playlist scheme generation is complete, don't forget to double check it!")
    return result

def ProcessCover():
    current_dir = os.getcwd()
    files_list = [f for f in os.listdir(current_dir) if os.path.isfile(os.path.join(current_dir ,f))]
    pattern = re.compile("cover", re.I)
    cover_processed = False
    for i in files_list:
        match = pattern.search(i)
        if (match):
            try:
                stream = ffmpeg.input(current_dir + "\\" + match.string)
                stream = ffmpeg.output(stream, "cover.jpg", **{"frames:v": "1"})
                ffmpeg.run(stream)
                cover_processed = True
            except:
                cover_processed = False
            finally:
                if cover_processed:
                    os.system("del " + '\"' + current_dir + "\\" + match.string + '\"')
    return cover_processed

def downloader(url: str):
    import pytubefix
    import bs4
    music_pos = url.find('music.youtube')
    if music_pos > 0:
        url = url[:music_pos] + url[music_pos + 6:]
    base_html = QtRendererWarp(url).html
    ytb_soup = bs4.BeautifulSoup(base_html, "html5lib")    
    content_info = {}
    music_list = ytb_soup.find_all("script")
    for it in music_list:
        if type(it.contents) == list and len(it.contents) > 0 and it.contents[0][0:19] == 'var ytInitialData =':
            content_info = json.decoder.JSONDecoder().decode(it.contents[0][20:-1])
    playlist_data = None
    if "twoColumnBrowseResultsRenderer" in content_info["contents"]: #Music album
        playlist_data = content_info["contents"]["twoColumnBrowseResultsRenderer"]["tabs"][0]["tabRenderer"]["content"]["sectionListRenderer"]["contents"][0]["itemSectionRenderer"]["contents"][0]["playlistVideoListRenderer"]["contents"]
    elif "twoColumnWatchNextResults" in content_info["contents"]: #Custom user playlist
        playlist_data = content_info["contents"]["twoColumnWatchNextResults"]["playlist"]["playlist"]  
    scheme = format_json_sceme(content_info, playlist_data)
    with open("format.json", "wb") as scheme_file:
        scheme_file.write(json.dumps(scheme, ensure_ascii=False, indent=1).encode())
    base_link = 'http://youtube.com/watch?v='
    first_hight_res = True
    output_path = os.getcwd()
    if "contents" in playlist_data:
        playlist_data = playlist_data["contents"]
    for i in list (playlist_data):
        id_link = None
        if "playlistVideoRenderer" in i:
            id_link = i["playlistVideoRenderer"]["videoId"]
        elif "playlistPanelVideoRenderer" in i:
            id_link = i["playlistPanelVideoRenderer"]["videoId"]
        else:
            print("Failed to parse youtube page...")
            break
        vid = pytubefix.YouTube(base_link + id_link)
        track = vid.streams.get_audio_only()
        if track:
            track.download(output_path = output_path)
        if first_hight_res:
            first_hight_res = False
            stream = vid.streams.get_highest_resolution(False)
            stream.download(output_path = output_path, filename="cover" + stream.default_filename[stream.default_filename.find('.'):])
            ProcessCover()
    return

if __name__ == "__main__":
    args = sys.argv
    #Explicit
    if (len(args) > 2 and args[1] == '--downloader'):
        downloader(args[2])
    else:
        converter(args)