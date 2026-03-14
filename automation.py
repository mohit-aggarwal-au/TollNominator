"""
Playwright automation for Linkt/CityLink toll nomination form.
Single-page React app — URL never changes, navigate by watching headings/content.
"""
import time
import threading
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

LINKT_NOMINATION_URL = "https://www.linkt.com.au/toll-invoices/melbourne/nominate"
CHROME_CDP_URL = "http://localhost:9222"


class TollAutomator:
    def __init__(self):
        self.status = "idle"
        self.message = ""
        self.page = None
        self.browser = None
        self.playwright = None
        self._submit_event = threading.Event()
        self._cancel_event = threading.Event()

    def get_status(self):
        return {"status": self.status, "message": self.message}

    def _update(self, status, message):
        self.status = status
        self.message = message
        print(f"[Automator] {status}: {message}")

    def _debug_fields(self, label):
        try:
            inputs = self.page.query_selector_all("input, select, textarea")
            print(f"[Automator] DEBUG {label} — {len(inputs)} fields")
            for el in inputs:
                ph = el.get_attribute("placeholder") or ""
                nm = el.get_attribute("name") or ""
                id_ = el.get_attribute("id") or ""
                tp = el.get_attribute("type") or ""
                tag = el.evaluate("el => el.tagName.toLowerCase()")
                print(f"  {tag} type={tp} name='{nm}' id='{id_}' placeholder='{ph}'")
        except Exception as e:
            print(f"[Automator] DEBUG error: {e}")

    def _wait_for_heading(self, text, timeout=10000):
        """Wait for a specific heading/text to appear on the React SPA."""
        try:
            self.page.wait_for_selector(
                f'text="{text}", h1:has-text("{text}"), h2:has-text("{text}"), '
                f'h3:has-text("{text}"), p:has-text("{text}")',
                timeout=timeout
            )
            print(f"[Automator] ✓ Page confirmed: '{text}'")
            return True
        except Exception:
            print(f"[Automator] ⚠️  Heading not found: '{text}'")
            return False

    def _react_set(self, selector, value):
        """Set value on a React input using nativeInputValueSetter + events."""
        if not value or str(value) in ("None", "nan", ""):
            return False
        try:
            self.page.wait_for_selector(selector, timeout=5000, state="visible")
            # Escape single quotes in value for JS
            safe_value = str(value).replace("'", "\\'")
            self.page.evaluate(f"""() => {{
                const el = document.querySelector('{selector}');
                if (!el) return;
                const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                setter.call(el, '{safe_value}');
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                el.dispatchEvent(new FocusEvent('blur', {{ bubbles: true }}));
            }}""")
            # Verify value was set
            actual = self.page.evaluate(f"document.querySelector('{selector}')?.value")
            print(f"[Automator] ✓ react_set '{selector}' = '{actual}'")
            return actual == str(value)
        except Exception as e:
            print(f"[Automator] ⚠️  react_set failed '{selector}': {e}")
            return False

    def fill_nomination_form(self, toll: dict, driver: dict, nominator: dict):
        try:
            self._update("launching", "Connecting to your Chrome browser...")
            self.playwright = sync_playwright().start()

            try:
                self.browser = self.playwright.chromium.connect_over_cdp(CHROME_CDP_URL)
            except Exception:
                self._update("error",
                    "Could not connect to Chrome. Make sure Chrome is running with "
                    "--remote-debugging-port=9222.")
                return

            contexts = self.browser.contexts
            context = contexts[0] if contexts else self.browser.new_context()
            self.page = context.new_page()

            # ----------------------------------------------------------------
            # PAGE 1: Enter toll invoice number
            # ----------------------------------------------------------------
            self._update("navigating", "Opening Linkt nomination page...")
            self.page.goto(LINKT_NOMINATION_URL, wait_until="networkidle", timeout=30000)
            self.page.wait_for_timeout(3000)

            self._update("filling", "Entering toll invoice number...")
            invoice_number = toll.get("notice_number") or toll.get("infringement_number") or ""

            invoice_selector = None
            for sel in ['input[placeholder="Toll invoice number"]',
                        'input[placeholder*="invoice"]', 'input[placeholder*="Invoice"]',
                        'input[id*="invoice"]', 'input[name*="invoice"]']:
                try:
                    self.page.wait_for_selector(sel, timeout=8000, state="visible")
                    invoice_selector = sel
                    break
                except Exception:
                    continue

            if not invoice_selector:
                self._update("error", "Could not find Toll invoice number field.")
                return

            self.page.fill(invoice_selector, invoice_number)
            self.page.wait_for_timeout(500)
            self._safe_click('button:has-text("Nominate toll invoice"), button:has-text("Nominate")')
            self.page.wait_for_timeout(3000)

            # ----------------------------------------------------------------
            # PAGE 2: Trip details — wait for table then click Continue
            # ----------------------------------------------------------------
            self._update("filling", "Confirming trip details...")
            # Wait for trip table to appear
            try:
                self.page.wait_for_selector('table, td, th, .trip', timeout=8000)
                print("[Automator] ✓ Trip details table found")
            except Exception:
                print("[Automator] ⚠️  Trip table not found, proceeding anyway")
            self.page.wait_for_timeout(1000)
            self._safe_click('button:has-text("Continue")')
            self.page.wait_for_timeout(3000)

            # ----------------------------------------------------------------
            # PAGE 3: YOUR details (nominator)
            # Wait for "Your details" section — NOT "Nominee details"
            # ----------------------------------------------------------------
            self._update("filling", "Filling YOUR (nominator) details...")

            # Wait specifically for "Your details" heading
            try:
                self.page.wait_for_selector(
                    'text="Your details"', timeout=10000)
                print("[Automator] ✓ Page 3 'Your details' confirmed")
            except Exception:
                print("[Automator] ⚠️  'Your details' heading not found, trying anyway")

            self.page.wait_for_selector('input[name="firstName"]', timeout=8000, state="visible")
            self.page.wait_for_timeout(1000)

            # Print what heading is visible RIGHT NOW
            heading = self.page.evaluate("() => document.querySelector('h1,h2,h3,.heading')?.textContent?.trim()")
            print(f"[Automator] Page 3 heading: '{heading}'")

            # Print nominator data we are about to fill
            print(f"[Automator] Nominator data: {nominator}")

            # Click the firstName field first to focus it
            self.page.click('input[name="firstName"]')
            self.page.wait_for_timeout(300)

            # Try triple approach: react_set + type + verify
            fn = str(nominator.get("first_name", ""))
            ln = str(nominator.get("last_name", ""))

            # 1. React setter
            self._react_set('input[name="firstName"]', fn)
            self._react_set('input[name="lastName"]', ln)
            self.page.wait_for_timeout(300)

            # 2. Verify — if empty, fall back to keyboard typing
            vals = self.page.evaluate("""() => ({
                first: document.querySelector('input[name="firstName"]')?.value,
                last: document.querySelector('input[name="lastName"]')?.value
            })""")
            print(f"[Automator] After react_set — firstName='{vals['first']}' lastName='{vals['last']}'")

            if not vals['first']:
                print("[Automator] react_set failed — falling back to keyboard typing")
                self.page.click('input[name="firstName"]')
                self.page.keyboard.press("Control+a")
                self.page.keyboard.press("Backspace")
                for char in fn:
                    self.page.keyboard.press(char)
                    self.page.wait_for_timeout(30)
                self.page.keyboard.press("Tab")
                self.page.wait_for_timeout(200)

            if not vals['last']:
                self.page.click('input[name="lastName"]')
                self.page.keyboard.press("Control+a")
                self.page.keyboard.press("Backspace")
                for char in ln:
                    self.page.keyboard.press(char)
                    self.page.wait_for_timeout(30)
                self.page.keyboard.press("Tab")
                self.page.wait_for_timeout(200)

            # Final verify
            vals2 = self.page.evaluate("""() => ({
                first: document.querySelector('input[name="firstName"]')?.value,
                last: document.querySelector('input[name="lastName"]')?.value
            })""")
            print(f"[Automator] FINAL page 3 values — firstName='{vals2['first']}' lastName='{vals2['last']}'")

            # Click first radio
            try:
                radios = self.page.query_selector_all('input[name="userStatement"]')
                if radios:
                    radios[0].click()
                    self.page.evaluate("""() => {
                        const el = document.querySelectorAll('input[name="userStatement"]')[0];
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }""")
                    print("[Automator] ✓ Radio clicked")
            except Exception as e:
                print(f"[Automator] ⚠️  Radio failed: {e}")

            self.page.wait_for_timeout(400)
            self._safe_click('button:has-text("Individual")')
            self.page.wait_for_timeout(500)

            # Click Continue — wait for page to transition to "Nominee details"
            self._safe_click('button:has-text("Continue")')

            # Wait for page 4 — "Nominee details" heading
            try:
                self.page.wait_for_selector('text="Nominee details"', timeout=10000)
                print("[Automator] ✓ Page 4 'Nominee details' confirmed")
            except Exception:
                print("[Automator] ⚠️  'Nominee details' heading not found")
                # Debug what's on screen now
                self._debug_fields("after page 3 Continue")
                heading = self.page.evaluate("document.querySelector('h1,h2,h3')?.textContent")
                print(f"[Automator] Current heading: {heading}")

            self.page.wait_for_timeout(2000)

            # ----------------------------------------------------------------
            # PAGE 4: Nominee (driver) details
            # Fields: firstName, lastName, Address (autocomplete), checkbox
            # ----------------------------------------------------------------
            if driver:
                self._update("filling", "Filling nominee (driver) details...")
                self._debug_fields("page 4 fields")

                self.page.wait_for_selector('input[name="firstName"]', timeout=8000, state="visible")

                self._react_set('input[name="firstName"]', driver.get("first_name", ""))
                self._react_set('input[name="lastName"]', driver.get("last_name", ""))
                self.page.wait_for_timeout(400)

                # Address autocomplete — find by checking all visible text inputs
                self._update("filling", "Filling nominee address...")
                address_str = f"{driver.get('address', '')} {driver.get('suburb', '')} {driver.get('state', 'VIC')} {driver.get('postcode', '')}".strip()

                # Find the address field — it's NOT firstName/lastName/search
                # Try by placeholder, then by finding visible text inputs excluding known ones
                addr_filled = False
                addr_selectors = [
                    'input[placeholder="Address"]',
                    'input[placeholder*="ddress"]',
                    'input[id*="address"]',
                    'input[name*="address"]',
                    'input[aria-label*="address"]',
                    'input[aria-label*="Address"]',
                ]
                for sel in addr_selectors:
                    try:
                        self.page.wait_for_selector(sel, timeout=3000, state="visible")
                        self.page.click(sel)
                        self.page.type(sel, address_str, delay=80)
                        self.page.wait_for_timeout(2500)
                        # Click first autocomplete suggestion
                        for sug in ['[role="option"]:first-child', 'ul li:first-child',
                                    '.pac-item:first-child', '[class*="suggestion"]:first-child',
                                    '[class*="result"]:first-child']:
                            try:
                                self.page.wait_for_selector(sug, timeout=2000, state="visible")
                                self.page.click(sug)
                                print(f"[Automator] ✓ Address suggestion clicked via {sug}")
                                addr_filled = True
                                break
                            except Exception:
                                continue
                        if not addr_filled:
                            self.page.keyboard.press("ArrowDown")
                            self.page.wait_for_timeout(300)
                            self.page.keyboard.press("Enter")
                            print("[Automator] Address: pressed ArrowDown+Enter for suggestion")
                            addr_filled = True
                        break
                    except Exception:
                        continue

                if not addr_filled:
                    # Last resort — find all visible text inputs, skip known ones, use the remainder
                    print("[Automator] Trying to find address field by exclusion...")
                    try:
                        all_inputs = self.page.query_selector_all('input[type="text"]:visible, input:not([type]):visible')
                        for inp in all_inputs:
                            nm = inp.get_attribute("name") or ""
                            id_ = inp.get_attribute("id") or ""
                            if nm in ("firstName", "lastName", "q") or id_ in ("firstName", "lastName", "header_input_search"):
                                continue
                            # This must be the address field
                            inp.click()
                            inp.type(address_str, delay=80)
                            self.page.wait_for_timeout(2500)
                            for sug in ['[role="option"]:first-child', 'ul li:first-child',
                                        '.pac-item:first-child']:
                                try:
                                    self.page.wait_for_selector(sug, timeout=2000, state="visible")
                                    self.page.click(sug)
                                    addr_filled = True
                                    break
                                except Exception:
                                    continue
                            if not addr_filled:
                                self.page.keyboard.press("ArrowDown")
                                self.page.wait_for_timeout(300)
                                self.page.keyboard.press("Enter")
                                addr_filled = True
                            print(f"[Automator] ✓ Address filled via exclusion (name='{nm}' id='{id_}')")
                            break
                    except Exception as e:
                        print(f"[Automator] ⚠️  Address exclusion failed: {e}")

                self.page.wait_for_timeout(1000)

                # Tick confirmation checkbox
                self._update("filling", "Ticking confirmation checkbox...")
                chk_filled = False
                for chk in ['input[type="checkbox"]', 'label:has-text("read and understood")',
                            'label:has-text("true and correct")', '[type="checkbox"]']:
                    try:
                        self.page.wait_for_selector(chk, timeout=3000, state="visible")
                        self.page.click(chk)
                        print(f"[Automator] ✓ Checkbox ticked via {chk}")
                        chk_filled = True
                        break
                    except Exception:
                        continue

                if not chk_filled:
                    # Try JS click on any checkbox
                    try:
                        self.page.evaluate("""() => {
                            const cb = document.querySelector('input[type="checkbox"]');
                            if (cb) { cb.click(); cb.dispatchEvent(new Event('change', {bubbles:true})); }
                        }""")
                        print("[Automator] ✓ Checkbox clicked via JS")
                    except Exception as e:
                        print(f"[Automator] ⚠️  Checkbox JS click failed: {e}")

                self.page.wait_for_timeout(500)

                # Click Continue
                self._update("filling", "Proceeding from nominee page...")
                self._safe_click('button:has-text("Continue"), button:has-text("Next")')
                self.page.wait_for_timeout(3000)

            # ----------------------------------------------------------------
            # PAUSE — wait for user to review
            # ----------------------------------------------------------------
            self._update("awaiting_review",
                         "✅ All fields filled. Review the browser, then click Submit in the app.")

            while not self._submit_event.is_set() and not self._cancel_event.is_set():
                time.sleep(0.5)

            if self._cancel_event.is_set():
                self._update("cancelled", "Automation cancelled.")
                self._cleanup()
                return

            # ----------------------------------------------------------------
            # SUBMIT
            # ----------------------------------------------------------------
            self._update("submitting", "Submitting nomination...")
            submitted = self._safe_click(
                'button:has-text("Submit"), button:has-text("Confirm"), '
                'button:has-text("Nominate"), button[type="submit"]'
            )
            if submitted:
                self.page.wait_for_timeout(3000)
                self._update("done", "✅ Nomination submitted successfully!")
            else:
                self._update("error", "Could not find Submit button — please click it manually.")

        except PlaywrightTimeoutError as e:
            self._update("error", f"Page timed out: {str(e)}")
        except Exception as e:
            self._update("error", f"Automation error: {str(e)}")
        finally:
            time.sleep(15)
            self._cleanup()

    # ----------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------

    def _react_set(self, selector, value):
        """Set React input value via nativeInputValueSetter + dispatch events."""
        if not value or str(value) in ("None", "nan", ""):
            return False
        try:
            self.page.wait_for_selector(selector, timeout=5000, state="visible")
            safe_value = str(value).replace("'", "\\'")
            self.page.evaluate(f"""() => {{
                const el = document.querySelector('{selector}');
                if (!el) return;
                const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                setter.call(el, '{safe_value}');
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                el.dispatchEvent(new FocusEvent('blur', {{ bubbles: true }}));
            }}""")
            actual = self.page.evaluate(f"() => document.querySelector('{selector}')?.value")
            print(f"[Automator] ✓ react_set '{selector}' = '{actual}'")
            return True
        except Exception as e:
            print(f"[Automator] ⚠️  react_set failed '{selector}': {e}")
            return False

    def _safe_click(self, selector: str) -> bool:
        for sel in [s.strip() for s in selector.split(",")]:
            try:
                self.page.wait_for_selector(sel, timeout=3000, state="visible")
                self.page.click(sel)
                print(f"[Automator] ✓ Clicked '{sel}'")
                return True
            except Exception:
                continue
        print(f"[Automator] ⚠️  Could not click: {selector[:80]}...")
        return False

    def _safe_type(self, selector: str, value: str) -> bool:
        if not value or value in ("None", "nan", ""):
            return False
        for sel in [s.strip() for s in selector.split(",")]:
            try:
                self.page.wait_for_selector(sel, timeout=3000, state="visible")
                self.page.click(sel)
                self.page.keyboard.press("Control+a")
                self.page.keyboard.press("Backspace")
                self.page.type(sel, value, delay=50)
                self.page.keyboard.press("Tab")
                return True
            except Exception:
                continue
        return False

    def submit(self):
        self._submit_event.set()

    def cancel(self):
        self._cancel_event.set()

    def _cleanup(self):
        try:
            if self.page:
                self.page.close()
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass
