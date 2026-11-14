"""Verify real-data ZODI correction defaults and on/off rebuilding in both views."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE'))
    page=browser.new_page(viewport={'width':1440,'height':1100});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:3001',wait_until='networkidle',timeout=90000)
    page.get_by_text('More options',exact=True).click()
    page.locator('.auto-pipeline>summary').click()
    checkbox=page.get_by_role('checkbox',name='Subtract zodiacal light (ZODI)',exact=True)
    expect(checkbox).to_be_checked()
    expect(page.locator('.auto-pipeline-evidence')).to_contain_text('IMAGE − ZODI',timeout=60000)
    expect(page.locator('.auto-pipeline li[data-complete=true]')).to_have_count(5,timeout=60000)
    sessions=[]
    for enabled in [False,True]:
        with page.expect_response(lambda r:r.url.endswith('/workspace/auto-session'),timeout=90000) as response:
            checkbox.set_checked(enabled)
        result=response.value.json();assert response.value.ok,result
        assert result['grid']['subtract_zodi']==enabled
        sessions.append(result['id'])
        expect(page.locator('.auto-pipeline-evidence')).to_contain_text('IMAGE − ZODI' if enabled else 'ZODI subtraction off',timeout=60000)
        expect(page.locator('.auto-pipeline li[data-complete=true]')).to_have_count(5,timeout=60000)
        expect(page.get_by_role('img',name='Signed difference image',exact=True)).to_be_visible()
    assert sessions[0]!=sessions[1]
    page.wait_for_load_state('networkidle')
    out=Path('test-results');out.mkdir(exist_ok=True)
    page.screenshot(path=str(out/'zodi-simple-desktop.png'),full_page=True)
    page.get_by_role('button',name='Complex',exact=True).click()
    print('Simple toggles passed',flush=True)
    expect(page.locator('.sidebar-file .active-file')).to_be_visible(timeout=60000)
    page.get_by_role('button',name='Difference imaging',exact=True).click()
    expect(checkbox).to_be_checked()
    # Use the known independent pair selected by Simple; cached files can include
    # different releases or cutouts of the same exposure.
    pair=result['recommended_pair'];pair_ids=[result['frames'][pair[k]]['id'] for k in ('reference','new')]
    library=page.request.get('http://127.0.0.1:3001/api/science/library').json()['observations']
    expect(page.locator('.library-row')).to_have_count(len(library),timeout=60000)
    print('Complex library ready',flush=True)
    selected_indices=page.locator('.library-row input').evaluate_all('(inputs)=>inputs.flatMap((input,i)=>input.checked?[i]:[])')
    for index in selected_indices:page.locator('.library-row').nth(index).locator('input').uncheck()
    print('Cleared initial selection',flush=True)
    for file_id in pair_ids:
        index=next(i for i,o in enumerate(library) if o['id']==file_id)
        page.locator('.library-row').nth(index).locator('input').check()
    expect(page.get_by_role('button',name='Build fixed-sky view',exact=True)).to_be_enabled(timeout=60000)
    with page.expect_response(lambda r:r.url.endswith('/workspace/sessions'),timeout=90000) as response:
        page.get_by_role('button',name='Build fixed-sky view',exact=True).click()
    result=response.value.json();assert response.value.ok,result
    print('Complex corrected build passed',flush=True)
    assert result['grid']['subtract_zodi']
    expect(page.locator('.session-metrics')).to_contain_text('IMAGE − ZODI')
    checkbox.uncheck()
    expect(page.locator('.session-metrics')).to_have_count(0)
    with page.expect_response(lambda r:r.url.endswith('/workspace/sessions'),timeout=90000) as response:
        page.get_by_role('button',name='Build fixed-sky view',exact=True).click()
    result=response.value.json();assert response.value.ok,result
    assert not result['grid']['subtract_zodi']
    expect(page.locator('.session-metrics')).to_contain_text('ZODI subtraction off')
    # Evict the preserved Simple session deliberately; returning must rebuild it.
    for size in [16,24,32,40]:
        evicted=page.request.post('http://127.0.0.1:3001/api/science/workspace/sessions',data={**result['grid'],'ids':pair_ids,'size':size})
        assert evicted.ok,evicted.text()
    page.get_by_role('button',name='Simple',exact=True).click()
    expect(checkbox).to_be_checked()
    expect(page.locator('.auto-pipeline-evidence')).to_contain_text('IMAGE − ZODI',timeout=60000)
    expect(page.locator('.auto-pipeline li[data-complete=true]')).to_have_count(5,timeout=60000)
    page.set_viewport_size({'width':390,'height':844});page.wait_for_load_state('networkidle')
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
    page.screenshot(path=str(out/'zodi-simple-mobile.png'),full_page=True)
    assert not errors,errors
    browser.close()
    print('Passed ZODI defaults, real corrected subtraction, Simple on/off recomputation, Complex invalidation/rebuild, cache separation, view retention and mobile layout.')
