/* Browser regression for CommentCut Bulk Desktop Studio v2 (Custom Folders + Video Meme). */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('../.venv/Lib/site-packages/playwright/driver/package');

const root = path.resolve(__dirname, '..');
const output = path.join(root, '.ui-check');
const screenshots = process.argv.includes('--screenshots');

const background = {
  id: 'a'.repeat(32),
  kind: 'background',
  name: 'Minecraft_Parkour_HD.mp4',
  file: 'Minecraft_Parkour_HD.mp4',
  source_folder: 'Vid_nen',
  bytes: 15_400_000,
};
const memeVid = {
  id: 'e'.repeat(32),
  kind: 'meme_video',
  name: 'huh_cat.mp4',
  file: 'huh_cat.mp4',
  source_folder: 'vid_meme',
  bytes: 820_000,
};
const memeImg = {
  id: 'b'.repeat(32),
  kind: 'image',
  name: '1.png',
  file: '1.png',
  source_folder: 'img_meme',
  bytes: 84_000,
};
const memeSnd = {
  id: 'c'.repeat(32),
  kind: 'sound',
  name: '1.mp3',
  file: '1.mp3',
  source_folder: 'mp3_meme',
  bytes: 52_000,
};
const thumbId = 'd'.repeat(32);
const captureSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="1280"><rect width="720" height="1280" fill="#181c27"/><rect x="40" y="280" width="640" height="220" rx="16" fill="#ffffff"/><text x="72" y="355" font-family="sans-serif" font-size="28" fill="#111">Ảnh chụp bình luận thật</text></svg>';

(async () => {
  if (screenshots) fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true, timeout: 12000 });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 920 } });
    page.setDefaultTimeout(8000);

    const errors = [];
    const previews = [];
    const submittedBatches = [];
    const appendedUrls = [];
    const rerendered = [];
    let presetSaved = null;
    let settings = { elevenlabs_key: false, elevenlabs_voice: '', elevenlabs_voices: ['', '', ''], elevenlabs_model: 'eleven_v3' };
    let storedBatches = [];
    let customFolders = { background: '', meme_video: '', image: '', sound: '' };

    function currentMediaDiag() {
      const defaults = { background: 'Vid_nen', meme_video: 'vid_meme', image: 'img_meme', sound: 'mp3_meme' };
      const folders = {};
      for (const k of ['background', 'meme_video', 'image', 'sound']) {
        const custom = customFolders[k];
        folders[k] = {
          kind: k,
          default_sub: defaults[k],
          path: custom || `C:/CommentCut/data/${defaults[k]}`,
          display_path: custom || `data/${defaults[k]}`,
          is_custom: !!custom,
          exists: true,
          count: 1,
        };
      }
      return {
        background_count: 1,
        meme_video_count: 1,
        meme_image_count: 1,
        meme_sound_count: 1,
        paired_meme_count: 1,
        random_paired_count: 0,
        missing_sounds: [],
        unpaired_images: [],
        folders,
      };
    }

    const crawlDays = [
      {
        date: '2026-11-18',
        project_count: 2,
        comment_count: 54,
        rendered_videos: 3,
        projects: [
          {
            id: '1'.repeat(32),
            name: 'Chuyện công sở cuối năm cười xỉu',
            url: 'https://www.threads.com/@minh_office/post/ABC123',
            author: 'minh_office',
            thumbnail: thumbId,
            project_folder: 'project1',
            comment_count: 30,
            selected_count: 30,
            crawled_at: '2026-11-18T01:30:00+07:00',
            crawl_date: '2026-11-18',
            job: {
              id: '2'.repeat(32),
              status: 'done',
              progress: 100,
              message: 'Hoàn tất',
              output_project: 'project1',
              files: ['Chuyện công sở - phần 01.mp4', 'Chuyện công sở - phần 02.mp4', 'Chuyện công sở - phần 03.mp4'],
            },
          },
          {
            id: '3'.repeat(32),
            name: '@review_dao · 741888999',
            url: 'https://www.tiktok.com/@review_dao/video/741888999',
            author: 'review_dao',
            thumbnail: thumbId,
            project_folder: 'project2',
            comment_count: 24,
            selected_count: 24,
            crawled_at: '2026-11-18T01:42:00+07:00',
            crawl_date: '2026-11-18',
            job: null,
          },
        ],
      },
    ];

    page.on('pageerror', e => errors.push(e.message));
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text());
    });

    await page.route('**/*', async route => {
      const req = route.request();
      const url = new URL(req.url());
      const pathname = url.pathname;

      if (pathname === '/' || pathname.startsWith('/static/')) {
        const file = path.join(root, pathname === '/' ? 'static/index.html' : pathname);
        const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.ttf': 'font/ttf' }[path.extname(file)];
        await route.fulfill({ path: file, contentType: mime });
        return;
      }
      if (pathname === '/api/card-preview' || pathname === `/api/assets/${thumbId}/file` || pathname === `/api/assets/${memeImg.id}/file`) {
        await route.fulfill({ body: captureSvg, contentType: 'image/svg+xml' });
        return;
      }
      if (pathname.startsWith('/api/assets/') && pathname.endsWith('/file')) {
        await route.fulfill({ status: 204 });
        return;
      }
      if (pathname === '/api/health') {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ ok: true, ffmpeg: true, data: 'C:/CommentCut/data', media: currentMediaDiag() }),
        });
        return;
      }
      if (pathname === '/api/media-folders/pick') {
        const body = req.postDataJSON();
        const pickedPath = `D:/Kho_Media_Rieng/${body.kind}`;
        customFolders[body.kind] = pickedPath;
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ picked: true, path: pickedPath, media: currentMediaDiag() }),
        });
        return;
      }
      if (pathname === '/api/media-folders') {
        if (req.method() === 'POST') {
          const body = req.postDataJSON();
          customFolders[body.kind] = body.path || '';
        }
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify(currentMediaDiag()) });
        return;
      }
      if (pathname === '/api/preset') {
        if (req.method() === 'POST') presetSaved = req.postDataJSON();
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify(presetSaved || {
            limit: 30,
            auto_render: true,
            options: {
              provider: 'elevenlabs',
              split_mode: 'comments',
              comments_per_video: 10,
              video_count: 3,
              resolution: 720,
              speed: 1.1,
              use_meme_video: false,
              use_meme_image: true,
              use_meme_sound: true,
              read_post: true,
              credit: 'CRE: COMMENTCUT',
              card_y: 0.28,
              max_seconds: 120,
              meme_volume: 0.65,
              elevenlabs_voices: [''],
            },
          }),
        });
        return;
      }
      if (pathname === '/api/assets') {
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify([background, memeVid, memeImg, memeSnd]) });
        return;
      }
      if (pathname === '/api/settings') {
        if (req.method() === 'POST') {
          const incoming = req.postDataJSON();
          settings = {
            ...settings,
            ...incoming,
            elevenlabs_key: incoming.elevenlabs_key ? true : settings.elevenlabs_key,
          };
        }
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify(settings) });
        return;
      }
      if (pathname === '/api/voice-preview') {
        previews.push(req.postDataJSON());
        await route.fulfill({ status: 200, contentType: 'audio/wav', body: Buffer.alloc(44) });
        return;
      }
      if (pathname === '/api/crawl-days') {
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify(crawlDays) });
        return;
      }
      if (pathname === '/api/projects/render-bulk') {
        const body = req.postDataJSON();
        rerendered.push(...body.project_ids);
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ queued_count: body.project_ids.length, failed: [], jobs: [] }) });
        return;
      }
      if (pathname === '/api/batch-crawl' && req.method() === 'GET') {
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify(storedBatches) });
        return;
      }
      if (pathname === '/api/batch-crawl' && req.method() === 'POST') {
        const body = req.postDataJSON();
        submittedBatches.push(body);
        const batchObj = {
          id: '4'.repeat(32),
          status: 'running',
          created: Date.now() / 1000,
          total: body.urls.length,
          completed: 1,
          message: `Đang crawl 2/${body.urls.length} · Đã quét 42 cmt · giữ 26/30 ảnh nhiều tim nhất`,
          items: body.urls.map((u, idx) => ({
            url: u,
            status: idx === 0 ? 'done' : 'crawling',
            name: idx === 0 ? 'Bài viết Threads đang hot hôm nay' : '',
            project_id: idx === 0 ? '1'.repeat(32) : '',
            comment_count: idx === 0 ? 30 : 0,
            message: idx === 0 ? 'Đã chụp 30 cmt · xếp hàng dựng 3 video MP4.' : 'Đã quét 42 cmt · giữ 26/30 ảnh nhiều tim nhất',
            job: idx === 0 ? { id: '2'.repeat(32), status: 'done', progress: 100, files: ['Part1.mp4', 'Part2.mp4', 'Part3.mp4'] } : null,
          })),
        };
        storedBatches = [batchObj];
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify(batchObj) });
        return;
      }
      if (pathname.startsWith('/api/batch-crawl/') && pathname.endsWith('/append')) {
        const body = req.postDataJSON();
        appendedUrls.push(...body.urls);
        for (const u of body.urls) {
          storedBatches[0].items.push({ url: u, status: 'queued', message: 'Mới thêm vào hàng đợi', comment_count: 0 });
        }
        storedBatches[0].total = storedBatches[0].items.length;
        storedBatches[0].status = 'done';
        storedBatches[0].completed = storedBatches[0].total;
        storedBatches[0].items.forEach(it => { it.status = 'done'; it.comment_count = 30; });
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ added: body.urls.length, skipped_duplicates: 0, total: storedBatches[0].total }) });
        return;
      }
      if (pathname.startsWith('/api/batch-crawl/')) {
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify(storedBatches[0]) });
        return;
      }
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ ok: true }) });
    });

    await page.goto('http://localhost:8766/');
    await page.waitForFunction(() => document.getElementById('sys-ffmpeg').textContent.includes('sẵn sàng'));

    // 1. Test Meme Checkbox Coupling:
    // Unchecking Sound automatically unchecks Image!
    assert.equal(await page.locator('#opt-meme-image').isChecked(), true);
    assert.equal(await page.locator('#opt-meme-sound').isChecked(), true);
    await page.locator('#opt-meme-sound').uncheck();
    assert.equal(await page.locator('#opt-meme-image').isChecked(), false);

    // Checking Video Meme alone works WITHOUT Image & Sound!
    await page.locator('#opt-meme-video').check();
    assert.equal(await page.locator('#opt-meme-video').isChecked(), true);
    assert.equal(await page.locator('#opt-meme-image').isChecked(), false);
    assert.equal(await page.locator('#opt-meme-sound').isChecked(), false);
    assert.match(await page.locator('#meme-rule-hint').innerText(), /Video Meme độc lập/);

    // Checking Image automatically checks Sound -> All 3 active!
    await page.locator('#opt-meme-image').check();
    assert.equal(await page.locator('#opt-meme-sound').isChecked(), true);
    assert.match(await page.locator('#meme-rule-hint').innerText(), /cả 3/);

    // 2. Test Custom Folder Picker right from Studio!
    await page.locator('#view-studio [data-pick-folder="meme_video"]').click();
    await page.waitForFunction(() => document.getElementById('studio-folder-meme_video').title.includes('Kho_Media_Rieng'));

    // 3. Configure ElevenLabs key + 3 Voice IDs
    await page.locator('#batch-urls').fill('https://www.threads.com/@u1/post/ONE\nhttps://www.tiktok.com/@u2/video/12345');
    await page.locator('.preflight-issue-btn').first().click();
    assert.equal(await page.locator('#view-voices').isVisible(), true);

    await page.locator('#elevenlabs_key').fill('sk-mock-eleven-key');
    await page.locator('#eleven-voice-1').fill('voice-intro-1');
    await page.locator('#eleven-voice-2').fill('voice-cmt-2');
    await page.locator('#eleven-voice-3').fill('voice-cmt-3');
    await page.getByRole('button', { name: '▶ Nghe giọng 3' }).click();
    assert.equal(previews.length, 1);
    await page.locator('#btn-save-voices').click();
    await page.waitForFunction(() => document.getElementById('eleven-status').textContent.includes('Đã lưu'));
    if (screenshots) {
      await page.locator('#notice').evaluate(el => { el.hidden = true; });
      await page.screenshot({ path: path.join(output, 'desktop-voices-1440.png') });
    }

    // 4. Launch Batch with ALL 3 Meme Types enabled + Custom Folder!
    await page.locator('[data-view="studio"]').click();
    assert.equal(await page.locator('#btn-start-batch').isEnabled(), true);
    if (screenshots) {
      await page.locator('#notice').evaluate(el => { el.hidden = true; });
      await page.screenshot({ path: path.join(output, 'desktop-studio-ready-1440.png') });
    }

    await page.locator('#btn-start-batch').click();
    await page.waitForFunction(() => document.getElementById('kpi-total').textContent === '2');
    assert.equal(submittedBatches.length, 1);
    assert.equal(submittedBatches[0].options.use_meme_video, true);
    assert.equal(submittedBatches[0].options.use_meme_image, true);
    assert.equal(submittedBatches[0].options.use_meme_sound, true);

    if (screenshots) {
      await page.locator('#notice').evaluate(el => { el.hidden = true; });
      await page.screenshot({ path: path.join(output, 'desktop-studio-running-1440.png') });
    }

    // 5. Dynamic append while batch is running
    await page.locator('#batch-urls').fill('https://www.threads.com/@u3/post/THREE');
    await page.locator('#btn-start-batch').click();
    await page.waitForFunction(() => document.getElementById('kpi-total').textContent === '3');
    assert.deepEqual(appendedUrls, ['https://www.threads.com/@u3/post/THREE']);

    // 6. History view
    await page.locator('[data-view="history"]').click();
    if (screenshots) {
      await page.locator('#notice').evaluate(el => { el.hidden = true; });
      await page.screenshot({ path: path.join(output, 'desktop-history-1440.png') });
    }
    await page.locator('#btn-bulk-rerender').click();
    assert.deepEqual(rerendered, ['3'.repeat(32)]);

    // 7. Library & Folders view (verify custom folder path & reset to default)
    await page.locator('[data-view="library"]').click();
    assert.match(await page.locator('#lib-path-meme_video').innerText(), /Kho_Media_Rieng/);
    assert.equal(await page.locator('#reset-folder-meme_video').isVisible(), true);
    if (screenshots) {
      await page.locator('#notice').evaluate(el => { el.hidden = true; });
      await page.screenshot({ path: path.join(output, 'desktop-library-1440.png') });
    }
    await page.locator('#reset-folder-meme_video').click();
    await page.waitForFunction(() => document.getElementById('lib-path-meme_video').textContent.includes('Mặc định'));

    // 8. Responsive overflow check across widths
    for (const [width, height] of [[1440, 920], [1200, 820], [960, 800], [680, 860], [390, 844]]) {
      await page.setViewportSize({ width, height });
      for (const view of ['studio', 'history', 'library', 'voices']) {
        await page.locator(`[data-view="${view}"]`).click();
        const noOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
        assert(noOverflow, `Horizontal overflow at ${width}x${height} on view=${view}`);
      }
    }

    const ids = await page.locator('[id]').evaluateAll(els => els.map(e => e.id));
    assert.equal(new Set(ids).size, ids.length, 'Duplicate DOM IDs detected');
    assert.deepEqual(errors, []);

    console.log('PASS: Custom Folders, Video Meme + Image/Sound rules, Bulk Studio, Responsive widths, 0 errors');
  } finally {
    await browser.close();
  }
})().catch(err => {
  console.error(err);
  process.exitCode = 1;
});
