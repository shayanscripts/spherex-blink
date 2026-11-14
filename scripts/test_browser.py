"""End-to-end validation against the configured real observation. Requires both servers."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root = Path(__file__).resolve().parent.parent
output = root / 'test-results'
output.mkdir(exist_ok=True)
with sync_playwright() as p:
    executable = os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE')
    browser = p.chromium.launch(headless=True, **({'executable_path': executable} if executable else {}))
    page = browser.new_page(viewport={'width':1440,'height':1100}, device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(os.environ.get('SPHEREX_APP_URL', 'http://127.0.0.1:3000'))
    page.wait_for_load_state('networkidle')
    page.get_by_role('button',name='Complex',exact=True).click()
    expect(page.get_by_text('FILE LOADED',exact=True)).to_be_visible(timeout=120000)
    expect(page.get_by_text('Rendering actual IMAGE pixels…')).to_have_count(0,timeout=30000)
    page.get_by_role('button',name='Inspect center pixel').click()
    expect(page.get_by_text('DETECTOR PIXEL',exact=True)).to_be_visible()
    page.screenshot(path=str(output/'real-desktop.png'),full_page=True)
    with page.expect_response(lambda response: response.request.method == 'POST' and response.url.endswith('/observations'),timeout=60000) as uploaded:
        page.locator('input[type=file]').set_input_files(str(root/'backend/data/spherex_full.fits'))
    assert uploaded.value.status == 200, uploaded.value.text()
    expect(page.get_by_text('Reading your FITS extensions, WCS, and wavelength calibration.',exact=False)).to_have_count(0,timeout=60000)
    expect(page.get_by_text('FILE LOADED',exact=True)).to_be_visible()
    for label in ['Variance','Quality flags','Zodiacal light','Science image']:
        page.get_by_role('tab',name=label).click()
        page.wait_for_load_state('networkidle')
        assert not page.get_by_text('This layer could not be rendered.',exact=False).count()
    page.get_by_role('button',name='Zoom in',exact=True).click()
    expect(page.get_by_text('130%',exact=True)).to_be_visible()
    page.get_by_role('button',name='Fit image',exact=True).click()
    page.get_by_role('button',name='Toggle detector grid').click()
    expect(page.get_by_role('button',name='Toggle detector grid')).to_have_attribute('aria-pressed','true')
    page.get_by_role('button',name='View FITS headers').click()
    expect(page.get_by_role('columnheader',name='KEYWORD')).to_be_visible()
    page.get_by_role('combobox').select_option('IMAGE')
    page.get_by_role('textbox',name='Search FITS keywords').fill('DATE-OBS')
    expect(page.get_by_role('cell',name='DATE-OBS',exact=True)).to_be_visible()
    expect(page.get_by_role('cell',name='2025-04-28T16:16:34.491',exact=True)).to_be_visible()
    page.get_by_role('button',name='Explore',exact=False).first.click()
    page.get_by_role('button',name='Open field guide').click()
    expect(page.locator('dialog')).to_be_visible()
    page.keyboard.press('Escape')
    expect(page.locator('dialog')).to_have_count(0)
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_load_state('networkidle')
    page.screenshot(path=str(output/'real-mobile.png'),full_page=True)
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), 'Mobile horizontal overflow'
    page.reload();page.wait_for_load_state('networkidle')
    expect(page.get_by_text('FILE LOADED',exact=True)).to_be_visible(timeout=120000)
    assert not errors, errors
    print('Browser checks passed: real dataset, four layers, pixel inspection, zoom, grid, headers, guide, responsive layout, cache restore; no runtime errors.')
    browser.close()
