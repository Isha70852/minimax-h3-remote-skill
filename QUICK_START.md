# MiniMax H3 Remote Colab Notebook 快速開始

## 1.安裝skill
請 Codex或手動安裝minimax-h3-remote-skill

## 2.Colab 第一次啟動

開啟colab，依照以下cell順序執行

Remote API 模式：

```text
Cell 1
  ↓
Cell 2：選 workflow / checkpoint / LoRA / VOSR2，按「套用設定」
  ↓
Cell 3：準備模型
  ↓
Cell 6：啟動 ComfyUI
  ↓
Cell 10：啟動 Remote API
```

Cell 10 會顯示：

```powershell
H3_API_URL="https://....trycloudflare.com"
H3_API_TOKEN="..."
```

貼到之後要啟動 Codex 的對話中或設定虛擬環境變數請Codex讀取。


## 3.生成影片

只有圖片：  

```text
使用minimax-h3-remote-skill
用專案資料夾example.png 做一支 10 秒真人電影感影片。雨夜東京街頭，人物往前走，最後回頭看鏡頭。不要配樂。輸出到專案"影片"資料夾。
提示詞自行查找minimax h3提示詞要求。
連接方式如以下:
H3_API_URL="https://xxxx.trycloudflare.com"
H3_API_TOKEN="xxxxxxxx"
```

圖片 + 動作影片 + 聲音： 

```text
用 person.png 當人物參考、walk.mp4 當動作和鏡頭參考、voice.wav 當聲音參考，做 8 秒 Ref2V，放到 C:\AI\outputs，前綴 walk_test。
```

Codex 會自己整理 prompt、送到 Colab、等待完成，最後下載 MP4 和 TXT。

## 4.手動生成
colab notebook也可以手動生成影片和放大影片，請依照colab notebook指示操作cell。

## 5.查看/比較影片-快速查看工具
1. 在video_viewer_server.py所在位置開啟 PowerShell。
2. 執行：

   ```powershell
   python video_viewer_server.py
   ```

3. 用瀏覽器開啟 <http://127.0.0.1:8787>。
4. 點右上角「資料夾來源」，輸入影片所在資料夾的完整路徑，再按「加入資料夾」。
5. 按「重新掃描」。查看器只會列出同一資料夾中檔名完全相同的配對：

   ```text
   example.mp4
   example.txt
   ```

直接執行時不會自動掃描目前工作區；來源位置會記住在 `video_viewer_sources.json`。