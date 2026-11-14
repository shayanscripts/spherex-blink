"""Check the default guided view, mode persistence and preserved complex workspace."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root=Path(__file__).resolve().parents[1];output=root/'test-results';output.mkdir(exist_ok=True)
with sync_playwright() as p:
    executable=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE')
    browser=p.chromium.launch(headless=True,**({'executable_path':executable} if executable else {}))
    page=browser.new_page(viewport={'width':1440,'height':1100});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.set_default_navigation_timeout(90000)
    page.goto(os.environ.get('SPHEREX_APP_URL','http://127.0.0.1:3001'));page.wait_for_load_state('networkidle')
    print('Initial page:',page.locator('h1').inner_text(),flush=True)
    expect(page.get_by_role('button',name='Simple',exact=True)).to_have_attribute('aria-pressed','true')
    expect(page.get_by_role('img',name='Signed difference image',exact=True)).to_be_visible(timeout=60000)
    page.wait_for_load_state('networkidle')
    page.screenshot(path=str(output/'simple-desktop.png'),full_page=True)
    # Exercise every enabled reference/date and the complete playback cycle.
    comparison_failures=[]
    page.on('response',lambda response:comparison_failures.append(response.status) if response.url.endswith('/analysis') and response.status>=400 else None)
    page.get_by_text('More options',exact=True).click()
    page.get_by_text('Dates & playback',exact=True).click()
    current_select=page.get_by_role('combobox',name='Simple current date')
    disabled=current_select.locator('option:disabled').count()
    assert disabled>0,'The real library should include explicitly unavailable dates'
    for option in current_select.locator('option:not(:disabled)').all():
        current_select.select_option(option.get_attribute('value'))
        expect(page.get_by_role('img',name='Signed difference image',exact=True)).to_be_visible(timeout=30000)
        page.wait_for_load_state('networkidle')
    original_reference=page.get_by_role('combobox',name='Simple reference date').input_value()
    for option in page.get_by_role('combobox',name='Simple reference date').locator('option:not(:disabled)').all():
        page.get_by_role('combobox',name='Simple reference date').select_option(option.get_attribute('value'))
        expect(page.get_by_role('img',name='Signed difference image',exact=True)).to_be_visible(timeout=30000)
        page.wait_for_load_state('networkidle')
    page.get_by_role('combobox',name='Simple reference date').select_option(original_reference)
    expect(page.get_by_role('img',name='Signed difference image',exact=True)).to_be_visible(timeout=30000)
    assert not comparison_failures,comparison_failures

    current_image=page.get_by_role('img',name='Current sky observation',exact=True)
    bounds=current_image.bounding_box();current_image.click(position={'x':bounds['width']*.75,'y':bounds['height']*.5})
    expect(page.locator('.simple-pick-position')).to_be_visible()
    page.get_by_role('button',name='Significance',exact=True).click()
    expect(page.get_by_role('img',name='Approximate significance image',exact=True)).to_be_visible()
    if page.get_by_role('button',name='Play animation',exact=True).is_enabled():
        page.get_by_role('combobox',name='Simple playback speed').select_option('2')
        page.get_by_role('button',name='Play animation',exact=True).click()
        expect(page.get_by_role('button',name='Pause animation',exact=True)).to_be_visible()
        page.wait_for_timeout(2500)
        page.get_by_role('button',name='Pause animation',exact=True).click()
        assert not comparison_failures,comparison_failures
    page.get_by_role('button',name='Wavelength Explorer',exact=True).click()
    expect(page.get_by_role('slider',name='Simple wavelength slider')).to_be_visible()
    expect(page.get_by_role('img',name='Measured detector pixels at the selected wavelength')).to_be_visible()
    page.get_by_role('slider',name='Simple wavelength slider').fill('4.99')
    page.wait_for_load_state('networkidle')
    page.get_by_role('button',name='Motion Explorer',exact=True).click()
    previous=page.get_by_role('combobox',name='Simple current date').input_value()
    page.get_by_role('button',name='Complex',exact=True).click()
    expect(page.get_by_role('button',name='Complex',exact=True)).to_have_attribute('aria-pressed','true')
    expect(page.get_by_role('navigation',name='Science navigation')).to_be_visible()
    page.get_by_role('button',name='Simple',exact=True).click()
    expect(page.get_by_role('combobox',name='Simple current date')).to_have_value(previous)
    page.set_viewport_size({'width':390,'height':844});page.wait_for_load_state('networkidle')
    expect(page.locator('.simple-app .simple-image-message')).to_have_count(0,timeout=30000)
    page.screenshot(path=str(output/'simple-mobile.png'),full_page=True)
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),'Mobile overflow'
    page.get_by_role('button',name='Complex',exact=True).click();page.reload();page.wait_for_load_state('networkidle')
    expect(page.get_by_role('button',name='Complex',exact=True)).to_have_attribute('aria-pressed','true')
    page.get_by_role('button',name='Simple',exact=True).click();page.reload();page.wait_for_load_state('networkidle')
    expect(page.get_by_role('button',name='Simple',exact=True)).to_have_attribute('aria-pressed','true')
    assert not errors,errors
    print('Passed: default Simple, real comparison, pixel inspection, significance, playback, wavelength control, both views, state retention, persisted preference and mobile overflow checks.',flush=True)
    browser.close()
