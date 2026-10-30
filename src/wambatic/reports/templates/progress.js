(function () {
  'use strict';
  const data = JSON.parse(document.getElementById('progress-data').textContent);

  // The addresses are built here from the job id and this page's own query, so nothing in the
  // embedded data can send the page elsewhere.
  const jobId = String(data.job);
  const progressPath = '/api/progress?job=' + encodeURIComponent(jobId);
  const query = new URLSearchParams(location.search);
  query.set('job', jobId);
  const reloadPath = '/report?' + query.toString();
  const stateElement = document.getElementById('state');
  const countsElement = document.getElementById('counts');
  const errorElement = document.getElementById('error');
  const retryElement = document.getElementById('retry');
  const labels = {
    queued: 'Waiting for another sync to finish',
    listing: 'Listing repositories',
    syncing: 'Syncing repositories',
    done: 'Done, loading the report',
    failed: 'The sync failed',
  };

  function fail(message) {
    errorElement.textContent = message;
    errorElement.hidden = false;
    retryElement.hidden = false;
  }

  function show(body) {
    stateElement.textContent = labels[body.state] || body.state;
    if (body.repos_pending !== null) {
      const rows = body.rows_written === null ? 0 : body.rows_written;
      countsElement.textContent =
        body.repos_done + ' of ' + body.repos_pending + ' repositories synced of ' +
        body.repos_listed + ' listed, ' + rows + ' rows written';
    } else if (body.repos_listed !== null) {
      countsElement.textContent = body.repos_listed + ' repositories listed';
    }
  }

  async function poll() {
    try {
      const response = await fetch(progressPath, { cache: 'no-store' });
      const body = await response.json();
      if (!response.ok) {
        stateElement.textContent = 'The sync cannot be followed';
        fail(body.error);
        return;
      }
      show(body);
      if (body.state === 'done') {
        location.replace(reloadPath);
        return;
      }
      if (body.state === 'failed') {
        fail(body.error);
        return;
      }
    } catch (error) {
      stateElement.textContent = 'Cannot reach the server, trying again';
    }
    setTimeout(poll, 1000);
  }

  poll();
})();
