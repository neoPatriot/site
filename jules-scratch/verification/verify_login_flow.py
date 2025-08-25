from playwright.sync_api import sync_playwright, expect

def run_verification():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Go to home page and verify the login button
        page.goto("http://127.0.0.1:8000/")
        page.wait_for_load_state('networkidle')
        expect(page.get_by_role("link", name="Регистрация / Войти")).to_be_visible()
        page.screenshot(path="jules-scratch/verification/home_with_login_button.png")

        # Click the login button and go to the login page
        page.get_by_role("link", name="Регистрация / Войти").click()
        page.wait_for_url("http://127.0.0.1:8000/login/")
        page.wait_for_load_state('networkidle')

        # Verify the login page content
        expect(page.get_by_role("heading", name="Вход или Регистрация")).to_be_visible()
        # The Telegram widget is in an iframe, so we check for the frame's presence
        expect(page.frame_locator('iframe[id^="telegram-login-"]').locator('button')).to_be_visible()
        page.screenshot(path="jules-scratch/verification/login_page.png")

        browser.close()

if __name__ == "__main__":
    run_verification()
