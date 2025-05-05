> [!IMPORTANT]
> This script is aimed to make music collection for your personal device is easy as it could be.
> Since hillariaous blockage of youtube i wasn't able to listen a simple part of my favorite music.
> Use it only for your own needs.

## Dependencies:
> * [beautifulsoup4](https://pypi.org/project/beautifulsoup4/) - HTML parsing, searching.
> * [ffmpeg-python](https://pypi.org/project/ffmpeg-python/) - FFmpeg wrap, i used to have direct calls to executable, but this does that for me.
> * [pytubefix](https://pypi.org/project/pytubefix/) ```Download engine V1``` - Fixed variant of pytube lib. May be broken. Requires Node.js to proceed as anonymous downloader.
> * [yt-dlp](https://pypi.org/project/yt-dlp/) ```Download engine V2``` - Extern linked cmd executable, written on python3. Heavily overloaded youtube downloader. Works all of the time, does not require Node.js.
> * [PyQtWebEngine](https://pypi.org/project/PyQtWebEngine-Qt5/) - HTML processing, executing as much js scripts ASSWECAN.
> * [requests](https://pypi.org/project/requests/) - Data requesting lib. Required to download high res cover if there is any.
## Dependencies auto-resolving:
I`ve integrated auto pip dependencies installer for required libs (does not affect nodejs). To make it work use ``` -module_check or --mc ```
command.

## Format.json:
Original idea was to format a formless media files into a good looking audio tracks so it can be iterated 
and recognizable as complete album. Any data that script is processing is formatted via json.
Songs or albims are presented with:

```
{
	"default": {"Author":"", "Year":"", "Album":"", "cover": ""}, 
	"1": ["Track Name", {"cover": "explicit_track_cover.jpg"}, {"author": "Additional Author Name"}, {"file": "explicit_file_name.?"}]
}
```

Where "default" is main data of complete album or track.
"1" : ["Name", ... ] others values exist to extend functionality for:
> 1) Diffrent covers f.e singles of albums.
> 2) Multiple authors on single track of specific track.
> 3) Track name contains platform banned symbols, or Track name is too complex to process it.

## Usage:
### 1. Prepare metadata of single track.
By default why processing a downloading link, all required data will be generated,
this prameter exist for cases if you missed or deleted originally generated "format.json" (of course you can do it on your own).
> Command requires following args: --pm "link" or -prepare_meta "link"

### 2. Downloading single track or complete album.
To download a single track and generate a "format.json" file for it, to process it later with ffmpeg,
 you need to provide argumets: --d "link" or -download "link"
> Command requires following args: --d "link" or -download "link"
> Default work mode is pytubefix, to use yt-dlp specify --y or -yt-dlp.

### 3. Processing prepared data.
After prepearing format.json on your own, or getting it from previous step
just execute script with no args.
Convert part of this script however have it`s own argument list, for reasons you already did some of steps on your own.
> For example: --skip (options) "convert" | "cover" | "tags"