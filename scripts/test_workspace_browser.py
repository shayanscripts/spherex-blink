"""Native-browser real-data checks for the multi-observation workspace."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root=Path(__file__).resolve().parents[1];output=root/'test-results';output.mkdir(exist_ok=True)
with sync_playwright() as p:
    executable=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE')
    browser=p.chromium.launch(headless=True,**({'executable_path':executable} if executable else {}))
    page=browser.new_page(viewport={'width':1440,'height':1100});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(os.environ.get('SPHEREX_APP_URL','http://127.0.0.1:3001'));page.wait_for_load_state('networkidle')
    page.get_by_role('button',name='Complex',exact=True).click()
    expect(page.get_by_text('FILE LOADED',exact=True)).to_be_visible(timeout=30000)
    page.get_by_role('button',name='Wavelengths',exact=True).click()
    page.wait_for_load_state('networkidle')
    expect(page.get_by_role('slider',name='Detector wavelength slider')).to_be_visible()
    expect(page.get_by_role('button',name='Build fixed-sky view')).to_be_enabled()
    page.get_by_role('button',name='Build fixed-sky view').click()
    expect(page.get_by_text('Registering observations…',exact=False)).to_have_count(0,timeout=60000)
    expect(page.get_by_text('Combined fixed-sky wavelength view',exact=True)).to_be_visible(timeout=60000)
    page.get_by_role('checkbox',name='Only measurements in selected wavelength interval').check()
    page.get_by_role('button',name='Build fixed-sky view').click()
    expect(page.get_by_text('Combined fixed-sky wavelength view',exact=True)).to_be_visible(timeout=60000)
    expect(page.locator('img[src*="/coadd"]')).to_be_visible()
    page.wait_for_load_state('networkidle')
    page.screenshot(path=str(output/'wavelength-workspace.png'),full_page=True)
    page.get_by_role('checkbox',name='Only measurements in selected wavelength interval').uncheck()
    page.get_by_role('button',name='Build fixed-sky view').click()
    expect(page.get_by_text('Combined fixed-sky wavelength view',exact=True)).to_be_visible(timeout=60000)
    page.get_by_role('button',name='Timeline',exact=True).click()
    expect(page.get_by_role('button',name='Play',exact=True)).to_be_enabled()
    old=page.get_by_role('combobox',name='Current observation frame').input_value()
    page.get_by_role('button',name='Next observation',exact=True).click()
    assert page.get_by_role('combobox',name='Current observation frame').input_value()!=old
    page.get_by_role('button',name='Play',exact=True).click();expect(page.get_by_role('button',name='Pause',exact=True)).to_be_visible();page.get_by_role('button',name='Pause',exact=True).click()
    image=page.locator('img[src*="/frames/"]');image.click(position={'x':150,'y':150})
    expect(page.get_by_text('Sky-grid pixel evidence',exact=True)).to_be_visible()
    page.wait_for_load_state('networkidle')
    expect(page.locator('.js-plotly-plot').first).to_be_visible(timeout=30000)
    page.screenshot(path=str(output/'timeline-workspace.png'),full_page=True)
    page.get_by_role('button',name='Difference imaging',exact=True).click()
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/analysis'),timeout=60000) as response:
        page.get_by_role('button',name='Compute comparison',exact=True).click()
    assert response.value.status==200,response.value.text()
    analysis=response.value.json();print('Real comparison:',json.dumps(analysis),flush=True)
    page.wait_for_load_state('networkidle')
    expect(page.get_by_text('Approximate significance',exact=True)).to_be_visible()
    page.locator('img[src*="kind=significance"]').click(position={'x':100,'y':100})
    expect(page.get_by_text('Sky-grid pixel evidence',exact=True)).to_be_visible()
    page.screenshot(path=str(output/'difference-workspace.png'),full_page=True)
    page.get_by_role('button',name='Investigate',exact=True).click()
    page.get_by_role('button',name='Find residual groups',exact=True).click()
    expect(page.get_by_text('Tentative motion associations',exact=True)).to_be_visible(timeout=30000)
    track_buttons=page.get_by_role('button',name='Test across dates',exact=False)
    if track_buttons.count():
        track_buttons.first.click();expect(page.get_by_text('PATH EVIDENCE',exact=True)).to_be_visible(timeout=60000)
    page.screenshot(path=str(output/'investigate-workspace.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(output/'workspace-mobile.png'),full_page=True)
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),'Mobile overflow'
    page.get_by_role('button',name='Find observations',exact=True).click()
    expect(page.get_by_role('button',name='Search IRSA at this position')).to_be_visible()
    assert not errors,errors
    print('Passed: real wavelength selection and coadd, registered epochs/playback, aperture charts, difference/significance, candidate groups, navigation, mobile layout; no runtime errors.')
    browser.close()
