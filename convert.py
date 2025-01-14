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

o_format = ".m4a"

ffmpeg_exe = "ffmpeg.exe"
exif_exe = "exiftool.exe"

ffmpeg_arg_1 = "-map 0:a -c:a aac"
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
            cmd = " -i "
            cmd += "\"" + current_dir + "\\" + i + "\""
            cmd += " -frames:v 1 cover.jpg"
            async_task_await(ffmpeg_exe, cmd)
            res = True
            g_album_info[0].CoverPath = "cover.jpg"
            break
    if (res == False):
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
            g_album_info.append(record)
    if cover_extraction_required:
        ExtractCover(default_data.CoverPath)

    return len(g_album_info) > 1

def add_tags(songId : int):
    current_dir = os.getcwd() + '\\' + g_working_dir
    files_list = [f for f in os.listdir(current_dir) if os.path.isfile(os.path.join(current_dir,f))]
    it = g_album_info[songId]
    pattern = re.compile(it.TrackName.replace('(',"\\(").replace(')',"\\)").replace('\'',"\'"), re.I)
    for i in files_list:
        match = pattern.search(i)
        if (match):
            src_path = "\"" + current_dir + '\\' + i + "\""
            tmp_path = "\"" + current_dir + '\\' + "tmp_" + i + "\""
            cmd = " -i " + src_path
            cmd += " -metadata " + " artist=" + "\"" + g_album_info[0].AuthorName + '\"'
            cmd += " -metadata " + " album=" + "\"" + g_album_info[0].AlbumName + '\"'
            cmd += " -metadata " + " date=" + "\"" + str(g_album_info[0].Year) + '\"'
            cmd += " -metadata " + " track=" + "\"" + str(it.TrackId) + '\"'
            cmd += " -metadata " + " title=" + "\"" + it.TrackName + '\"'
            cmd += " -c:0 copy " + tmp_path
            async_task_await(ffmpeg_exe, cmd)
            os.system("del " + src_path)
            os.system("move " + tmp_path + ' ' + src_path)
            res = True
            break
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

    pattern = re.compile(it.TrackName.replace('(',"\\(").replace(')',"\\)"), re.I)
    res = False
    for i in files_list:
        match = pattern.search(i)
        if (match):
            src_path = '\"' + current_dir + '\\' + g_working_dir + '\\' + i + '\"'
            tmp_path = '\"' + current_dir + '\\' + g_working_dir + '\\' + "tmp_" + i + '\"'
            cmd = " -i " + src_path
            cmd += " -i " + '\"' + current_dir + '\\' + g_working_dir + '\\' + cover_path + '\"'
            cmd += " -map 0 -map 1 -c copy -disposition:1 attached_pic " + tmp_path
            async_task_await(ffmpeg_exe, cmd)
            os.system("del " + src_path)
            os.system("move " + tmp_path + ' ' + src_path)
            res = True
            break
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
            cmd = " -i "
            cmd += "\"" + current_dir + "\\" + match.string + "\" "
            cmd += ffmpeg_arg_1 + " \"" + current_dir + "\\" + g_working_dir + "\\" + g_album_info[0].AuthorName + ' - ' + it.TrackName + o_format + "\""
            async_task_await(ffmpeg_exe, cmd)
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

def main(args):
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

if __name__ == "__main__":
    main(sys.argv)