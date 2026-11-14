"""Exercise automatic real-library selection, residual thresholds and matched inspection."""
import os,re
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE'))
    page=browser.new_page(viewport={'width':1440,'height':1100})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(os.environ.get('SPHEREX_APP_URL','http://127.0.0.1:3001'),wait_until='networkidle',timeout=90000)
    page.locator('.auto-pipeline>summary').click()
    page.locator('.residual-results>summary').click()
    page.get_by_text('More options',exact=True).click()
    expect(page.locator('.auto-pipeline')).to_be_visible()
    expect(page.get_by_role('img',name='Signed difference image',exact=True)).to_be_visible(timeout=60000)
    expect(page.locator('.auto-pipeline li[data-complete=true]')).to_have_count(5,timeout=30000)
    with page.expect_response(lambda r:'/candidates?threshold=10&' in r.url) as response:
        page.get_by_role('combobox',name='Residual significance threshold').select_option('10')
    result=response.value.json();assert response.value.ok
    assert all(abs(r['peak_sigma'])>=10 and r['pixels']>=3 for r in result['candidates'])
    expect(page.locator('.residual-marker')).to_have_count(len(result['candidates']))
    if result['candidates']:
        page.locator('.residual-list>button').first.click()
        expect(page.locator('.simple-pick-position')).to_be_visible()
        page.locator('.residual-marker').first.click(force=True)
        expect(page.locator('.simple-pick-position')).to_be_visible()
    with page.expect_response(lambda r:r.url.endswith('/workspace/auto-session')) as response:
        page.get_by_role('button',name='Find & compare automatically',exact=True).click()
    session=response.value.json();assert response.value.ok
    pair=session['recommended_pair'];assert pair
    assert session['frames'][pair['reference']]['timestamp']<session['frames'][pair['new']]['timestamp']
    expect(page.locator('.auto-pipeline li[data-complete=true]')).to_have_count(5,timeout=60000)
    expect(page.get_by_role('checkbox',name='Match background levels')).to_be_checked()
    page.wait_for_load_state('networkidle')
    expect(page.locator('.residual-results .auto-pipeline-heading strong')).to_have_text(re.compile(r'\d+ highlighted differences'),timeout=60000)
    expect(page.locator('.auto-pipeline li[data-complete=true]')).to_have_count(5)
    output=Path('test-results');output.mkdir(exist_ok=True)
    page.screenshot(path=str(output/'automatic-comparison-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844});page.wait_for_load_state('networkidle')
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
    page.screenshot(path=str(output/'automatic-comparison-mobile.png'),full_page=True)
    assert not errors,errors
    browser.close()
    print('Passed automatic pair selection, five pipeline stages, threshold filtering, residual markers, pixel inspection, rerun and mobile layout.')
