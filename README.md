# MiniMax H3 Remote Colab Notebook 使用說明

查看[QUICK_START](https://github.com/Isha70852/minimax-h3-remote-skill/blob/main/QUICK_START.md)

這套工具的用途很單純：**Colab 負責跑 MiniMax H3 / VOSR2，Codex 或其他 agent 負責整理提示詞、上傳參考素材、等待生成，最後把 MP4 和 TXT 下載回電腦。**

不需要安裝 `google-colab-cli`。

## 先把 Colab 開起來

每次新的 Colab runtime，依序執行：

```text
Cell 1
  ↓
Cell 2
  ↓
Cell 3
  ↓
Cell 6
  ↓
Cell 10
```
Cell 2 選好你要的生成模式、主模型、LoRA、Sampler、Scheduler，以及要不要直接用 VOSR2 放大，然後按 「套用設定」。  
Cell 3 會準備你選到的模型。  
Cell 6 啟動 ComfyUI。  
Cell 10 啟動給 Windows 使用的 HTTPS API。執行成功後會看到類似：

```powershell
$env:H3_API_URL="https://xxxx.trycloudflare.com"
$env:H3_API_TOKEN="xxxxxxxx"
```

把這兩行貼到之後要啟動 Codex 的同一個對話視窗。
如果 Colab runtime 重開，或 Cell 10 重跑，URL / Token 會換，所以要重新貼一次。

## 平常最簡單的用法

直接跟 Codex/agent 說你要什麼，不一定要自己寫完整 prompt。  
例如只有一張人物參考圖：

```text
使用minimax-h3-remote-skill
用專案資料夾example.png 做一支 10 秒真人電影感影片。雨夜東京街頭，人物往前走，最後回頭看鏡頭。不要配樂。輸出到專案"影片"資料夾。
提示詞自行查找minimax h3提示詞要求。
連接方式如以下:
H3_API_URL="https://xxxx.trycloudflare.com"
H3_API_TOKEN="xxxxxxxx"
```

Codex 會自己整理 MiniMax H3 prompt，呼叫 Colab，等生成完成，再把 MP4 和 TXT 下載回來。

## Ref2V 可以同時用圖片、影片和聲音

Ref2V 的三種參考素材是分開編號的：
``` text
第一個 --image  -> <Picture 1>
第二個 --image  -> <Picture 2>

第一個 --video  -> <Video 1>
第二個 --video  -> <Video 2>

第一個 --audio  -> <Audio 1>
第二個 --audio  -> <Audio 2>
```

數量上限：
``` text
Picture：0–9
Video：0–3
Audio：0–3
```

Ref2V 三種素材加起來至少要有一個。
影片參考會同時把影片畫面和影片本身的 audio stream 送進 Ref2V。--audio 則是額外的獨立聲音參考。

例如你可以跟 Codex 說：
用 person.png 保留人物長相，用 dance.mp4 參考動作和鏡頭，用 voice.wav 參考聲音，做一支 8 秒影片。

Codex 應該會把 prompt 寫成類似：
``` text
Use <Picture 1> as the identity reference.
Use <Video 1> as the motion and camera-motion reference.
Use <Audio 1> as the voice/audio reference.
```

手動呼叫 client 的寫法：
``` powershell
python scripts\h3_client.py generate `
  --image "C:\AI\refs\person.png" `
  --video "C:\AI\refs\dance.mp4" `
  --audio "C:\AI\refs\voice.wav" `
  --prompt-file "C:\AI\work\prompt.txt" `
  --mode ref2v_native `
  --duration 8 `
  --output-dir "C:\AI\outputs" `
  --prefix "H3_Remote_Colab"
```

如果要多個參考，就重複同一個參數：
```powershell
--image "front.png" --image "side.png"
--video "motion1.mp4" --video "motion2.mp4"
--audio "voice.wav" --audio "ambience.wav"
```

順序很重要，不要交換；因為順序就是 \<Picture N>、\<Video N>、\<Audio N> 的編號。

## I2V 和 T2V

I2V 只使用圖片：
--image 第 1 張 = first frame  
--image 第 2 張 = last frame（可省略）

I2V 不要傳 Ref2V 的 --video 或 --audio。  
T2V 不需要任何 --image、--video 或 --audio。

## 指定模型與 LoRA

平常不用指定，client 會沿用 Cell 2 現在的設定。
如果要臨時換成 Colab 裡已經存在的模型，先看清單：
```text
python scripts\h3_client.py models
```

再把清單中的完整檔名放進 --model 或 --lora：
```powershell
python scripts\h3_client.py generate `
  --image "C:\AI\refs\person.png" `
  --prompt-file "C:\AI\work\prompt.txt" `
  --mode ref2v_native `
  --model "minimax_h3_fl2va_pruned_int8_convrot.safetensors" `
  --lora "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors" `
  --steps 8 `
  --sampler res_multistep `
  --scheduler simple `
  --output-dir "C:\AI\outputs" `
  --prefix "fl2va_ref"
```

這裡的 mode 是「怎麼接 conditioning」，checkpoint / LoRA 是另一件事，所以 Ref2V 可以配你要測試的 FL2VA checkpoint / LoRA。
如果不要 LoRA：
```powershell
--no-lora
```

## Sampler / Scheduler

常用 Sampler：  
res_multistep  
euler  
er_sde  

常用 Scheduler：  
simple  
beta  
normal

client 會把你輸入的名稱直接交給 ComfyUI；如果該名稱不存在，server 會回錯誤。

## 生成時直接用 VOSR2 放大

例如想以 1080p 為目標：
```powershell
python scripts\h3_client.py generate `
  --image "C:\AI\refs\person.png" `
  --prompt-file "C:\AI\work\prompt.txt" `
  --upscale-to 1920x1080 `
  --fit-side long `
  --output-dir "C:\AI\outputs" `
  --prefix "H3_Remote_Colab"
```

VOSR2 會保持原本比例，不裁切、不硬拉伸。  
--fit-side long：讓長邊對到指定尺寸的長邊。  
--fit-side short：讓短邊對到指定尺寸的短邊。  
所以來源比例不是剛好 16:9 時，實際結果可能是 1920x1067、1944x1080 這種接近值，這是正常的。  
Inline VOSR2 完成後只保留最後放大版，不另外下載一份原始解析度 MP4。

## 只放大已經存在的影片

如果 H3 影片已經生成好了，只想再放大，不要重新跑 H3：
```powershell
python scripts\h3_client.py upscale `
  --video "C:\AI\outputs\preview.mp4" `
  --target 1920x1080 `
  --fit-side long `
  --output-dir "C:\AI\outputs" `
  --prefix "H3_Remote_Colab"
```

這個命令裡的 --video 是「要被放大的影片」。
而 generate --video 是「Ref2V 的 \<Video N> 參考影片」。兩者不要混淆。

## 輸出檔名

建議讓 Codex / agent 使用 --output-dir + --prefix，不要自己硬寫最終檔名。
一般生成：
前綴_YYYYMMDD-HHMMSS_seedSEED.mp4
前綴_YYYYMMDD-HHMMSS_seedSEED.txt
例如：
H3_Remote_Colab_20261003-143812_seed735812345.mp4
H3_Remote_Colab_20261003-143812_seed735812345.txt

有 VOSR2 時會再加實際尺寸：
H3_Remote_Colab_20261003-143812_seed735812345_1920x1067.mp4
H3_Remote_Colab_20261003-143812_seed735812345_1920x1067.txt.

TXT 不是臨時 prompt 的副本。它是 Colab 端真正留下的生成紀錄，會記錄實際使用的模式、主模型、LoRA、seed、尺寸、Sampler、Scheduler、Picture / Video / Audio 對應、VOSR2 設定，以及最後送給 H3 的完整 prompt。

## 常見問題

如果 health 連不上，通常是 Colab runtime 已中斷，或 Cell 10 的 Quick Tunnel 已失效。回 Colab 重跑 Cell 10，再把新的兩行環境變數貼到 PowerShell。
如果回 401 Unauthorized，通常也是 Token 已經換掉。
如果說找不到主模型或 LoRA，先跑：
```powershell
python scripts\h3_client.py models
```
如果清單真的沒有，回 Colab用 Cell 2 選好來源，再跑 Cell 3。
如果說 <Video 2>、<Audio 1> 之類不存在，檢查 prompt 裡的編號和你實際傳入的檔案數量是否一致。
如果 VOSR2 / VHS 節點不存在，回 Colab 重新執行 Cell 1，建議重啟 runtime，再執行 Cell 6 和 Cell 10。

## 致謝

感謝以下開源專案與作者：

- MiniMax H3：https://github.com/MiniMax-AI/MiniMax-H3
- ComfyUI：https://github.com/comfy-org/comfyui
- killkli：https://github.com/killkli/minimax-h3-colab-skill/tree/main
