# Tiến độ dự án

_Cập nhật lần cuối: 2026-10-22_

## Đã xong
- [x] Kế hoạch: `Implementation-Plan.md` (dùng **OpenAI**, mục tiêu portfolio, deploy Render)
- [x] `docker-compose.yml` (n8n **2.44.4** + Postgres **17**), `.env` (secret đã sinh ngẫu nhiên), `render.yaml`
- [x] Workflow: SYS-01, SYS-02, ONB-01. Đã import vào n8n local, ID được giữ nguyên, 27/27 node khớp schema của n8n
- [x] Đã tạo tài khoản owner n8n (http://localhost:5678)

## Đang làm: chuẩn bị dịch vụ (`docs/setup-M1-part1.md` mục 3)
- [ ] **Phần 1A: Google Sheet** → Sheet ID
- [ ] **Phần 1B: Telegram** → Alerts chat ID, Errors chat ID (bot token chỉ nhập trong n8n)
- [ ] Phần 2: ClickUp → List ID, Template ID (custom field ID là tùy chọn)
- [ ] Phần 3: Slack app → workspace invite link (bot token chỉ nhập trong n8n)
- [ ] Phần 4: Stripe test mode + Payment Link (custom field key `company`, metadata `plan_name`)
- [ ] Phần 5: Google Cloud OAuth (Gmail API + Sheets API)
- [ ] Điền các ID vào Config (sửa `tools/gen_workflows.py`, sinh lại, import lại)
- [ ] Tạo credential trong n8n và gán vào node (**làm sau cùng**, vì import lại sẽ xóa credential đã gán)
- [x] Chọn tunnel **ngrok**: đã thêm service `ngrok` vào docker-compose, `WEBHOOK_URL` tự lấy từ `NGROK_DOMAIN`
- [ ] **Bạn cần làm:** tạo tài khoản ngrok, điền `NGROK_AUTHTOKEN` và `NGROK_DOMAIN` vào `.env` (xem setup doc mục 1)
- [ ] Test theo mục 6 của setup doc

## Tiếp theo
- M1 phần còn lại: SYS-03, SYS-04, ONB-02 đến ONB-10
- M2, M3, deploy Render, Demo Portal

## Mở lại môi trường
```powershell
# 1. Mở Docker Desktop, chờ khởi động xong
docker compose up -d          # dữ liệu n8n nằm trong Docker volume, không bị mất khi tắt máy
# 2. Mở http://localhost:5678
```

## Quy trình sửa workflow
Nguồn chính là `tools/gen_workflows.py`. Các file `workflows/*.json` được sinh từ script này.
```powershell
python -I tools\gen_workflows.py workflows          # sinh JSON
node tools\validate.js workflows                    # cú pháp JS + kết nối giữa node
# Kiểm tra bằng schema của chính n8n (chạy trong container):
Get-Content tools\schema_check.js | docker compose exec -T n8n sh -c "cat > /tmp/sc.js && node /tmp/sc.js"
docker compose exec n8n n8n import:workflow --separate --input=/home/node/workflows
```
⚠️ Nếu sửa workflow trong giao diện n8n thì phải đưa thay đổi đó vào script (hoặc export ra), vì import lại sẽ ghi đè.

## Lưu ý kỹ thuật
- Git Bash tự đổi đường dẫn `/home/node/...` thành đường dẫn Windows. Cần `export MSYS_NO_PATHCONV=1` trước lệnh `docker compose exec`, hoặc dùng PowerShell.
- PowerShell 5.1 làm hỏng dấu `"` khi truyền vào `docker exec sh -c`. Nên đưa script vào container qua stdin.
- Lệnh import ghi đè workflow có cùng ID và xóa phần gán credential.
