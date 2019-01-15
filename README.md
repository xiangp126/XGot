### XGot

[XGot](https://github.com/xiangp126/xgot) aims to download videos from [乐FUN影视](http://www.lefuntv.us/), can be a complement for [You-Get](https://github.com/soimort/you-get)

### Usage
#### clone repo

```git
git clone https://github.com/xiangp126/xgot
```

#### make link

```
cd /usr/local/bin
ln -s <path-to-xgot.py> xgot
```

#### download video
```bash
$ xgot http://www.lefuntv.us/index.php/vod/play/id/24302/sid/1/nid/1.html
```

default download path is `./videos`

### Tips
merge all `ts` into one, be patient to wait

```bash
cat *.ts > input.ts
```

convert `ts` to `mp4`

```bash
ffmpeg -i input.ts output.mp4 -y
```

### License
The [MIT](./LICENSE.txt) License (MIT)