# Cài đặt và test: SYS-01, SYS-02, ONB-01

| File | Workflow | Vai trò |
|---|---|---|
| `workflows/SYS-01_error-handler.json` | [SYS-01] Global Error Handler | Mọi lỗi được báo về Telegram group Errors |
| `workflows/SYS-02_notify-telegram.json` | [SYS-02] Notify Telegram | Sub-workflow gửi Telegram (`chat: alerts/errors`, `text`) |
| `workflows/ONB-01_stripe-kickoff.json` | [ONB-01] Stripe Payment → Kickoff | Thanh toán → Registry → ClickUp → Slack → Email → Telegram |

Luồng ONB-01:
```
Stripe Trigger → Remove Duplicate Events → Only Paid → Config → Normalize Client
→ Registry: Add Client → ClickUp: Create From Template → Prepare Provisioning
   ├─ Build Custom Fields → ClickUp: Set Custom Field
   └─ Slack: Create Channel → Slack Connect Enabled? ─(true)→ Slack: Invite ─┐
                                                    └─(false)──────────────────┴→ Slack: Welcome Message
      → Slack Result → Gmail: Welcome Email → Build Registry Update → Registry: Update Client
      → Build Telegram Message → Notify Telegram (SYS-02)
```
Nếu Slack hoặc email lỗi, workflow **vẫn chạy tiếp**: lỗi được ghi vào cột `notes`, `status` chuyển thành `needs_attention`, và tin Telegram có thêm mục "⚠️ Needs manual action". Các lỗi khác (Sheets, ClickUp) làm dừng workflow và SYS-01 sẽ báo lỗi.

---

## 1. Khởi động n8n
```powershell
Copy-Item .env.example .env      # điền POSTGRES_PASSWORD, N8N_ENCRYPTION_KEY, NGROK_AUTHTOKEN, NGROK_DOMAIN
docker compose up -d             # chạy cả n8n + Postgres + ngrok
```
Mở http://localhost:5678 và tạo tài khoản owner.

ngrok chạy như một service trong docker-compose với **domain tĩnh miễn phí**, nên URL webhook (`https://<NGROK_DOMAIN>/`) không đổi giữa các lần khởi động. Cách lấy token và domain:
1. Đăng ký tại https://dashboard.ngrok.com/signup
2. Menu **Getting Started → Your Authtoken** → copy vào `NGROK_AUTHTOKEN`
3. Menu **Domains** → copy domain dạng `xxx.ngrok-free.app` (tạo mới nếu chưa có) vào `NGROK_DOMAIN` (không có `https://`)

Kiểm tra: `docker compose logs ngrok` có dòng `started tunnel`, và mở `https://<NGROK_DOMAIN>/healthz` thấy `{"status":"ok"}`.

## 2. Import workflow
```powershell
docker compose exec n8n n8n import:workflow --separate --input=/home/node/workflows
```
Import bằng CLI **giữ nguyên ID workflow**, nên ONB-01 tự gọi đúng SYS-02 và tự gắn SYS-01 làm Error Workflow.

> Nếu import bằng giao diện (Import from File), ID sẽ đổi. Khi đó cần chọn lại SYS-02 trong node *Notify Telegram (SYS-02)*, và chọn lại SYS-01 trong *Settings → Error Workflow* của ONB-01 và SYS-02.

## 3. Chuẩn bị các dịch vụ

### Google Sheet (Client Registry)
1. Tạo Google Sheet mới, đổi tên tab thành `Clients`
2. File → Import → upload `sheets-template/Clients.csv` → chọn *Replace current sheet* (chỉ có dòng tiêu đề)
3. Copy **Sheet ID** (chuỗi giữa `/d/` và `/edit` trong URL)

### Telegram
1. Tạo bot qua @BotFather để lấy **bot token**
2. Tạo 2 group `Alerts` và `Errors`, thêm bot vào cả hai, gửi `/start@<tên_bot>` trong mỗi group (bot ở chế độ privacy chỉ nhận lệnh có `/`)
3. Mở `https://api.telegram.org/bot<TOKEN>/getUpdates` để lấy `chat.id`. Đây là một **số âm**: group thường có dạng `-4…`, supergroup có dạng `-100…`

### ClickUp
1. Settings → Apps → **API Token** (`pk_…`)
2. Tạo Space/List `Clients` để lấy **List ID** (số trong URL của list)
3. Tạo một task mẫu (checklist onboarding, subtask…) → menu `…` → *Templates → Save as Template*
4. Lấy **Template ID**: `GET https://api.clickup.com/api/v2/team/{team_id}/taskTemplate?page=0` (header `Authorization: pk_…`). ID có dạng `t-…`
5. (Tùy chọn) Lấy **custom field ID**: `GET https://api.clickup.com/api/v2/list/{list_id}/field`

### Slack
1. https://api.slack.com/apps → *Create New App* → *From scratch*
2. *OAuth & Permissions* → Bot Token Scopes: `channels:manage`, `channels:read`, `chat:write`
   (thêm `conversations.connect:write` nếu dùng Slack Connect với gói trả phí)
3. *Install to Workspace* để lấy **Bot token** (`xoxb-…`)
4. Gói Free: tạo **invite link** cho workspace (Invite people → Copy invite link) rồi điền vào Config

### Stripe (test mode)
1. Bật **Test mode** → Developers → API keys để lấy `sk_test_…`
2. Tạo Product (ví dụ "Outbound Growth – Monthly", recurring)
3. Tạo **Payment Link**:
   - *Add custom field* → Text, label "Company name", **key `company`**
   - *Advanced → Metadata*: `plan_name` = `Outbound Growth – Monthly`

### Google OAuth (Gmail + Sheets)
1. Google Cloud Console → tạo project → bật **Gmail API** và **Google Sheets API**
2. OAuth consent screen (External, thêm email của bạn làm test user)
3. Credentials → OAuth client ID (Web application) → Redirect URI = URL hiển thị trong cửa sổ tạo credential của n8n

## 4. Tạo credential trong n8n và gán vào node

| Credential (loại trong n8n) | Gán vào node |
|---|---|
| Telegram API | SYS-01 *Telegram: Send Error*, SYS-02 *Telegram: Send* |
| Stripe API (`sk_test_…`) | ONB-01 *Stripe Trigger* |
| Google Sheets OAuth2 API | *Registry: Add Client*, *Registry: Update Client* |
| ClickUp API | *ClickUp: Create From Template*, *ClickUp: Set Custom Field* |
| Slack API (bot token) | *Slack: Create Channel*, *Slack: Invite (Slack Connect)*, *Slack: Welcome Message* |
| Gmail OAuth2 | *Gmail: Welcome Email* |

## 5. Điền Config (tìm chữ `REPLACE_WITH_`)
- SYS-01 → node **Format Error**: `ERRORS_CHAT_ID`
- SYS-02 → node **Resolve Chat**: `alerts`, `errors`
- ONB-01 → node **Config**: Sheet ID, ClickUp list/template ID, Slack invite link, form URL, booking URL, tên agency

## 6. Test

### 6.1 Test nhanh bằng dữ liệu mẫu (không cần thanh toán)
1. Mở ONB-01 → node **Stripe Trigger** → *Edit Output* (pin data) → dán nội dung `mocks/stripe-checkout-session-completed.json`
   - Đổi `customer_details.email` thành email của bạn để nhận được email chào mừng
2. Bấm **Test workflow**
3. **Mỗi lần test lại phải đổi `"id"` của event** (ví dụ `evt_test_…0002`), vì node *Remove Duplicate Events* sẽ chặn event đã gặp

### 6.2 Test end-to-end thật
1. **Activate** SYS-02 và ONB-01 (SYS-01 không cần activate để làm Error Workflow). Khi activate, n8n tự đăng ký webhook trên Stripe
2. Mở Payment Link, thanh toán bằng thẻ `4242 4242 4242 4242`, ngày hết hạn trong tương lai, CVC bất kỳ
3. Kiểm tra:
   - [ ] Dòng mới trong `Clients`, `status = onboarding`
   - [ ] Task ClickUp tạo từ template, có custom field (nếu đã cấu hình)
   - [ ] Kênh Slack `client-<công-ty>-<6 số>` có tin chào mừng
   - [ ] Nhận email chào mừng
   - [ ] Telegram Alerts nhận tin "💰 New client paid"
   - [ ] Gửi lại event từ Stripe Dashboard (Events → Resend): **không** tạo thêm gì

### 6.3 Test xử lý lỗi
- **Lỗi mềm:** đổi Slack token thành chuỗi sai rồi thanh toán lại. Kết quả mong đợi: ClickUp và email vẫn chạy, `status = needs_attention`, Telegram có mục "Needs manual action"
- **Lỗi cứng:** đổi `clickup_list_id` thành giá trị sai. Kết quả mong đợi: group Errors nhận tin "🚨 Workflow failed" kèm link tới execution
  > Error Workflow chỉ được kích hoạt với execution **production** (workflow đang active, được trigger thật), không áp dụng khi bấm *Test workflow*

## 7. Giới hạn đã biết
- *Remove Duplicate Events* ghi nhận event **trước** khi các bước sau chạy xong. Nếu workflow lỗi giữa chừng, Stripe gửi lại sẽ bị bỏ qua, nên cần xử lý tay dựa trên Telegram alert (có đủ link execution để chạy lại).
- `client_id` sinh theo thời gian (`CL-yyMMdd-HHmmss`). Đủ cho demo; với lượng thanh toán lớn đồng thời nên đổi sang chuỗi ngẫu nhiên.
- Slack Connect (`conversations.inviteShared`) chỉ chạy trên workspace trả phí. Để `slack_connect_enabled: false` cho bản demo.
