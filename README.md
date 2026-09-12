# Jellycat 上架追蹤器

定時抓取 Jellycat 官網的商品目錄，偵測到**上架、補貨、新品、價格變動**時寄 Gmail 通知一份名單。跑在 GitHub Actions 上，不需要自己的伺服器。

**同時追蹤英國站和美國站**，這兩個是獨立的商店，庫存、價格、上架時間都可能不一樣：

| | 🇬🇧 jellycat.com | 🇺🇸 us.jellycat.com |
| --- | --- | --- |
| Searchspring siteId | `d3slzq` | `bmcyq0` |
| 目錄件數 | 約 575 | 約 711 |
| 幣別 | 英鎊 GBP | 美元 USD |

同一件商品在兩站是**分開追蹤**的，所以你會分別收到「英國站上架」和「美國站上架」的通知。

最重要的事件是 **Coming Soon → 正式上架**：官網會先把未發售商品標成 `Coming Soon`，而且常常直接公告日期（例如 `Available 16th September`）。追蹤器會在信裡先做上架倒數，真的開賣的那一輪再發出「🎉 正式上架」通知。

## 運作方式

Jellycat 官網是 BigCommerce 商店，站內搜尋由 Searchspring 提供。它的公開 JSON 端點一次就能拿到整份可購買目錄，所以這個專案**不需要解析 HTML、不需要瀏覽器**：

```
https://api.searchspring.net/api/search/search.json?siteId=<siteId>&resultsPerPage=100&page=N&resultsFormat=native
```

每次執行 = 兩站合計約 14 個請求。每天兩次 = 一天不到 30 個請求。

要增減追蹤的商店，改 [`src/fetch.py`](src/fetch.py) 裡的 `STORES` 清單即可。

用到的欄位：

| 欄位 | 用途 |
| --- | --- |
| `uid` | 快照主鍵的一半（實際是 `<店別>:<uid>`，商品改網址也不會被誤判成新品） |
| `ss_product_status` | `Live` / `Coming Soon` — 上架偵測的核心 |
| `ss_in_stock` | `1` / `0` — 補貨、售罄偵測 |
| `ss_badge_title` | `New In` / `Back in Stock` / `Available 16th September` … |
| `name` `sku` `custom_url` `price` `imageUrl` | 信件內容 |

每次抓完的結果存進 [`data/snapshot.json`](data/snapshot.json)，由 Actions 自己 commit 回 repo；下一次拿新資料跟它比對就得到事件。歷史事件會附加到 `data/events.jsonl`。

> 信件裡每一列都會標 🇬🇧 或 🇺🇸，價格也會用該站的幣別顯示。

## 通知的事件

全站都會通知：

| 事件 | 觸發條件 |
| --- | --- |
| 🎉 正式上架 | `Coming Soon` → `Live` |
| ✨ 全新商品 | 目錄裡出現沒看過的商品 |
| 📣 新公告：即將上架 | 新增的 `Coming Soon` 商品 |
| 📅 上架日期公布／異動 | badge 出現或改動具體日期 |
| 📦 補貨到 | 缺貨 → 有貨，**或**官網把 badge 換成 `Back in Stock` |

**只有追蹤清單裡的商品**才會通知（因為隨時都有兩百多件缺貨，全站通知會變成垃圾信）：

| 事件 | 觸發條件 |
| --- | --- |
| 🚫 售罄 | 有貨 → 缺貨 |
| 💷 價格變動 | 價格改變 |
| 👋 已下架 | 商品從目錄消失 |

補貨為什麼要看兩個訊號：排程是一天兩次，商品可能在兩次執行**之間**補貨又賣完 —— 前後快照都是「缺貨」，純比較庫存完全看不到。官網自己會給補貨商品掛 `Back in Stock` 標籤而且會留一陣子，用它當第二個訊號就能撈回這類漏掉的補貨（實測 67 件掛此標籤的商品全部真的有貨，零誤標）。這種來源的通知會額外註明「官網標記補貨」。

### 每封信都會附「我的追蹤清單」

信的最上方固定列出 `watchlist.txt` 命中的每一件商品和**目前狀態**，不管這輪有沒有變化：

- `尚未上架 · 官網尚未公告日期`
- `尚未上架 · 09/16 還有 4 天`
- `已上架 · 有貨` / `已上架 · 目前缺貨`

這樣「我等的那件到底上架了沒」永遠有答案，不用等它剛好在這一輪發生變化。

### 什麼時候會寄信

| 觸發 | 行為 |
| --- | --- |
| 早上 09:00 排程 | **一定寄**，當作每日狀態回報 |
| 下午 17:00 排程 | 只有偵測到變化才寄 |
| 手動 Run workflow | **一定寄**（不然按了按鈕沒反應很難確認有沒有設對） |

要改成「只有變化才寄」，把 [`track.yml`](.github/workflows/track.yml) 裡的 `ALWAYS_SEND` 那行改成 `ALWAYS_SEND: ''` 即可。追蹤清單是空的時候，沒變化就一樣不寄。

## 設定追蹤清單

編輯 [`watchlist.txt`](watchlist.txt)，一行一個關鍵字：

```
ulrich wolf
bartholomew bear
amuseables-birthday-cake-bag-charm
```

從商品網址取一段當關鍵字最準（例如 `us.jellycat.com/amuseables-birthday-cake-bag-charm/` 就填 `amuseables-birthday-cake-bag-charm`），這樣兩站的同一件商品會一起命中。

大小寫不拘，會比對商品的**名稱 / SKU / 網址**，包含就算命中。命中的商品在信裡標 ⭐ 並排在最前面。清單留空也能用，只是收不到上面那三種「清單限定」的通知。

## 一次性設定

### 1. 申請 Gmail 應用程式密碼

這一步只能你本人在自己的 Google 帳號操作：

1. 到 [Google 帳號安全性](https://myaccount.google.com/security)，確認**兩步驟驗證已開啟**（沒開就沒有應用程式密碼這個選項）。
2. 前往 [應用程式密碼](https://myaccount.google.com/apppasswords)。
3. 隨便取個名字（例如 `jellycat-tracker`）→ 建立。
4. 複製那組 **16 碼密碼**。它只會顯示一次，而且跟你的 Google 登入密碼是兩回事。

### 2. 設定 GitHub Secrets

到 repo 的 **Settings → Secrets and variables → Actions → New repository secret**，建立三個：

| 名稱 | 內容 |
| --- | --- |
| `GMAIL_USER` | 寄件用的 Gmail 地址，例如 `you@gmail.com` |
| `GMAIL_APP_PASSWORD` | 上一步那 16 碼（有沒有空格都可以） |
| `MAIL_TO` | 收件人，多人用逗號分隔：`a@x.com, b@y.com` |

收件人是放在 **Bcc**，所以名單上的人彼此看不到對方的信箱。

### 3. 跑第一次

到 **Actions → Jellycat Tracker → Run workflow** 手動觸發一次。第一次執行只會建立基準快照、不寄信 —— 因為沒有「上一次」可以比較。第二次開始才會有通知。

## 排程

[`.github/workflows/track.yml`](.github/workflows/track.yml) 設定每天跑兩次：

- **台北時間 09:00**（UTC 01:00）
- **台北時間 17:00**（UTC 09:00）—— 對應英國上午的上架尖峰

要改頻率就改 workflow 裡的 `cron`（**注意 GitHub 用的是 UTC**，台灣要減 8 小時）。

## 本機測試

不需要安裝任何套件，Python 3.11+ 即可（只用標準函式庫）。

```bash
python3 -m src.main --status    # 只問「我追的那幾件現在怎樣」，最快
python3 -m src.main --seed      # 建立基準快照，不寄信
python3 -m src.main --dry-run   # 印出事件、輸出信件 HTML 預覽，不寄信也不寫檔
```

`--status` 的輸出長這樣：

```
⭐ 我的追蹤清單（2 筆）
  🇬🇧 Amuseables Birthday Cake Bag Charm — £28 · 尚未上架 · 官網尚未公告日期
  🇺🇸 Amuseables Birthday Cake Bag Charm — $35 · 尚未上架 · 官網尚未公告日期
```

想驗證寄信管道有沒有通，用當下目錄寄一封示範信：

```bash
GMAIL_USER=you@gmail.com GMAIL_APP_PASSWORD='xxxx xxxx xxxx xxxx' MAIL_TO=you@gmail.com \
  python3 -m src.main --send-test
```

想測試事件偵測，手動改 `data/snapshot.json` 裡某幾筆（例如把 `"status"` 改成 `"Coming Soon"`、`"in_stock"` 改成 `false`），再跑 `--dry-run`。

## 穩健性

- 任何一頁抓三次都失敗 → 整場中止，**不覆蓋快照也不寄信**
- 任一店的商品數少於上次的 80% → 視為抓取異常，中止並保留舊快照（避免產生幾百筆假的「已下架」）。分店檢查，才不會被另一店的數量蓋過去
- 寄信失敗時**故意不更新快照**，這樣下一輪會重新偵測到同一批事件，不會漏掉
- `concurrency` 群組確保兩輪不會同時寫快照

## 已知限制

- **GitHub 排程會延遲**，通常 5–20 分鐘，尖峰時段更久。不保證準時。
- GitHub 會停用**連續 60 天無活動**的 repo 排程。本專案每次執行都會 commit 快照，正常情況不會被停用。
- 價格是英鎊或美元，不是台幣。
- 目錄只涵蓋這兩個官網上架販售的商品，不含實體門市限定或其他區域站。
