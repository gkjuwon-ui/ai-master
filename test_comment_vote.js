const http = require('http');

function req(method, path, body) {
  return new Promise((resolve, reject) => {
    const opts = {
      hostname: 'localhost', port: 4000,
      path: '/api/community' + path,
      method,
      headers: {
        'Content-Type': 'application/json',
        'X-Runtime-Secret': 'ogenti-runtime-secret-2024'
      }
    };
    const r = http.request(opts, res => {
      let d = '';
      res.on('data', c => d += c);
      res.on('end', () => {
        try { resolve({ status: res.statusCode, data: JSON.parse(d) }); }
        catch(e) { resolve({ status: res.statusCode, data: d }); }
      });
    });
    r.on('error', reject);
    if (body) r.write(JSON.stringify(body));
    r.end();
  });
}

async function test() {
  // 1. Get posts
  console.log('=== STEP 1: Fetch posts ===');
  const posts = await req('GET', '/posts?limit=3&sortBy=recent');
  console.log('Posts status:', posts.status);
  if (!posts.data || !posts.data.data || !posts.data.data.posts || posts.data.data.posts.length === 0) {
    console.log('NO POSTS FOUND', JSON.stringify(posts.data).slice(0, 500));
    return;
  }
  const post = posts.data.data.posts[0];
  const title = (post.title || '').slice(0, 60);
  console.log('First post:', post.id, '"' + title + '"', 'commentCount:', post.commentCount);

  // 2. Get post detail with comments
  console.log('\n=== STEP 2: Get post detail ===');
  const detail = await req('GET', '/posts/' + post.id);
  console.log('Detail status:', detail.status);
  const comments = (detail.data && detail.data.data && detail.data.data.comments) ? detail.data.data.comments : [];
  console.log('Comments count:', comments.length);
  if (comments.length === 0) {
    console.log('NO COMMENTS found in detail response');
    console.log('Detail keys:', Object.keys(detail.data.data || {}));
    return;
  }
  
  // Show first 5 comments with their vote counts
  console.log('\nCurrent comment votes:');
  for (const c of comments.slice(0, 5)) {
    const content = (c.content || '').slice(0, 80);
    console.log('  [' + c.id + '] by ' + c.agentName + ' | score:' + c.score + ' up:' + c.upvotes + ' down:' + c.downvotes + ' | ' + content);
  }

  // 3. Try to vote on first comment using a DIFFERENT agent
  const targetComment = comments[0];
  // Use the agentId of comment[1] so it's a different agent voting
  const voterAgentId = comments.length > 1 ? comments[1].agentId : 'test-fake-agent';
  console.log('\n=== STEP 3: Vote on comment ' + targetComment.id + ' ===');
  console.log('Target comment by:', targetComment.agentName, '(agentId:', targetComment.agentId + ')');
  console.log('Voter agentId:', voterAgentId);
  
  const voteResult = await req('POST', '/comments/' + targetComment.id + '/vote', {
    value: 1,
    agentId: voterAgentId
  });
  console.log('Vote HTTP status:', voteResult.status);
  console.log('Vote result:', JSON.stringify(voteResult.data, null, 2));

  // 4. Check if vote was applied
  console.log('\n=== STEP 4: Re-fetch post to verify ===');
  const detail2 = await req('GET', '/posts/' + post.id);
  const comments2 = (detail2.data && detail2.data.data && detail2.data.data.comments) ? detail2.data.data.comments : [];
  const updated = comments2.find(function(c) { return c.id === targetComment.id; });
  if (updated) {
    console.log('BEFORE: score=' + targetComment.score + ' up=' + targetComment.upvotes + ' down=' + targetComment.downvotes);
    console.log('AFTER:  score=' + updated.score + ' up=' + updated.upvotes + ' down=' + updated.downvotes);
    if (updated.score !== targetComment.score) {
      console.log('>>> VOTE APPLIED SUCCESSFULLY <<<');
    } else {
      console.log('>>> VOTE DID NOT CHANGE SCORE <<<');
    }
  } else {
    console.log('Could not find comment after re-fetch');
  }

  // 5. Also test what happens with __AGENT_RUNTIME__ userId 
  // (this is what the runtime actually sends via X-Runtime-Secret header)
  console.log('\n=== STEP 5: Check authentication flow ===');
  console.log('Auth header being used: X-Runtime-Secret');
  console.log('This resolves userId to __AGENT_RUNTIME__ in the middleware');
  console.log('Then voteComment resolves it via _resolveRuntimeUserId');
}

test().catch(function(e) { console.error('ERROR:', e.message); });
