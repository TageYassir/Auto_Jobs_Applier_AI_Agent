// Tab switching
function showTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
    document.getElementById(tabId).style.display = 'block';
    // Update sidebar active
    document.querySelectorAll('#sidebarNav .nav-link').forEach(link => link.classList.remove('active'));
    document.querySelector(`[data-tab="${tabId}"]`).classList.add('active');
    // Load data when switching
    if (tabId === 'dashboard') updateStats();
    else if (tabId === 'config') loadConfig();
    else if (tabId === 'resume') { loadResume(); loadCvPreview(); }
    else if (tabId === 'logs') { logPage=1; document.getElementById('logsTableBody').innerHTML=''; loadLogs(); }
}

document.querySelectorAll('#sidebarNav .nav-link').forEach(link => {
    link.addEventListener('click', e => {
        e.preventDefault();
        showTab(link.getAttribute('data-tab'));
    });
});

// Dashboard stats
function updateStats() {
    fetch('/api/stats').then(r=>r.json()).then(d=>{
        document.getElementById('appliedCount').innerText = d.applied;
        document.getElementById('failedCount').innerText = d.failed;
        document.getElementById('skippedCount').innerText = d.skipped;
    });
    fetch('/api/status').then(r=>r.json()).then(d=>{
        const badge = document.getElementById('statusBadge');
        badge.textContent = d.running ? 'Running' : 'Stopped';
        badge.className = `badge fs-5 ${d.running ? 'bg-success' : 'bg-secondary'}`;
        document.getElementById('startBtn').disabled = d.running;
        document.getElementById('stopBtn').disabled = !d.running;
    });
    fetch('/api/status').then(r=>r.json()).then(d=>{
        if (d.last_run_status) document.getElementById('lastRunStatus').textContent = d.last_run_status;
    });
}

document.getElementById('startBtn').addEventListener('click', ()=> fetch('/api/start',{method:'POST'}).then(()=>updateStats()));
document.getElementById('stopBtn').addEventListener('click', ()=> fetch('/api/stop',{method:'POST'}).then(()=>updateStats()));

// Configuration
function loadConfig() {
    fetch('/api/config').then(r=>r.json()).then(cfg=>{
        document.getElementById('configManualPosition').value = cfg.manual_position || '';
        document.getElementById('configCountries').value = cfg.countries || '';
        document.getElementById('configContractTypes').value = cfg.contract_types ? JSON.stringify(cfg.contract_types) : '';
        document.getElementById('configExperienceLevel').value = cfg.experience_level ? JSON.stringify(cfg.experience_level) : '';
        document.getElementById('configRemote').checked = cfg.remote;
        document.getElementById('configHybrid').checked = cfg.hybrid;
        document.getElementById('configOnsite').checked = cfg.onsite;
        document.getElementById('configDistance').value = cfg.distance || 100;
        document.getElementById('configDateFilter').value = cfg.date_filter || '24_hours';
        document.getElementById('configApplyOnce').checked = cfg.apply_once_at_company;
        document.getElementById('configCompanyBlacklist').value = cfg.company_blacklist || '';
        document.getElementById('configTitleBlacklist').value = cfg.title_blacklist || '';
        document.getElementById('configLocationBlacklist').value = cfg.location_blacklist || '';
    });
}

document.getElementById('saveConfigBtn').addEventListener('click', ()=>{
    const data = {
        manual_position: document.getElementById('configManualPosition').value,
        countries: document.getElementById('configCountries').value,
        contract_types: JSON.parse(document.getElementById('configContractTypes').value || '[]'),
        experience_level: JSON.parse(document.getElementById('configExperienceLevel').value || '{}'),
        remote: document.getElementById('configRemote').checked,
        hybrid: document.getElementById('configHybrid').checked,
        onsite: document.getElementById('configOnsite').checked,
        distance: parseInt(document.getElementById('configDistance').value),
        date_filter: document.getElementById('configDateFilter').value,
        apply_once_at_company: document.getElementById('configApplyOnce').checked,
        company_blacklist: document.getElementById('configCompanyBlacklist').value,
        title_blacklist: document.getElementById('configTitleBlacklist').value,
        location_blacklist: document.getElementById('configLocationBlacklist').value,
    };
    fetch('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data)})
    .then(()=>alert('Configuration saved'));
});

// Resume
function loadResume() {
    fetch('/api/resume').then(r=>r.json()).then(d=>{ document.getElementById('resumeEditor').value = d.content; });
}
document.getElementById('saveResumeBtn').addEventListener('click', ()=>{
    const content = document.getElementById('resumeEditor').value;
    fetch('/api/resume', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({content})})
    .then(()=>alert('Resume saved'));
});

// CV Upload & Preview
function loadCvPreview() {
    fetch('/api/config').then(r=>r.json()).then(cfg=>{
        const preview = document.getElementById('cvPreview');
        const removeBtn = document.getElementById('removeCvBtn');
        if (cfg.cv_path) {
            preview.innerHTML = `<i class="bi bi-file-earmark-pdf text-danger"></i> Uploaded: <strong>${cfg.cv_path.split('/').pop()}</strong>`;
            removeBtn.style.display = 'inline-block';
        } else {
            preview.innerHTML = 'No CV uploaded';
            removeBtn.style.display = 'none';
        }
    });
}

document.getElementById('uploadCvBtn').addEventListener('click', ()=>{
    const fileInput = document.getElementById('cvFileInput');
    if (!fileInput.files.length) return alert('Select a PDF file first');
    const formData = new FormData();
    formData.append('cv_file', fileInput.files[0]);
    fetch('/api/upload_cv', {method:'POST', body:formData})
    .then(r=>r.json())
    .then(data=>{
        alert(data.message);
        loadCvPreview();
        fileInput.value = '';
    });
});

document.getElementById('removeCvBtn').addEventListener('click', ()=>{
    fetch('/api/remove_cv', {method:'POST'}).then(()=>loadCvPreview());
});

// Logs
let logPage = 1;
function loadLogs() {
    fetch('/api/logs?page='+logPage).then(r=>r.json()).then(d=>{
        const tbody = document.getElementById('logsTableBody');
        d.logs.forEach(l=>{
            tbody.innerHTML += `<tr><td>${l.timestamp}</td><td>${l.job_title}</td><td>${l.company}</td>
                <td><span class="badge ${l.status==='success'?'bg-success':l.status==='failed'?'bg-danger':'bg-warning'}">${l.status}</span></td>
                <td>${l.reason||''}</td></tr>`;
        });
        document.getElementById('loadMoreLogsBtn').style.display = d.has_next ? 'block' : 'none';
    });
}
document.getElementById('loadMoreLogsBtn').addEventListener('click', ()=>{ logPage++; loadLogs(); });

// Polling
setInterval(updateStats, 5000);

// Initial load
showTab('dashboard');