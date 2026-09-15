const {test}=require('node:test');
const assert=require('node:assert/strict');
const {trackunitAssetId}=require('../extension/context.js');
const id='00000000-0000-0000-0000-000000000001';
test('asset detail extracts only UUID',()=>{
 assert.equal(trackunitAssetId(`https://new.manager.trackunit.com/assets/${id}/status?token=do-not-copy#secret`),id);
 assert.equal(trackunitAssetId(`https://manager.trackunit.com/assets/${id}`),id);
});
test('reject wrong origin, list, admin, malformed and embedded identity',()=>{
 for(const url of [`http://new.manager.trackunit.com/assets/${id}`,
 `https://new.manager.trackunit.com.evil.test/assets/${id}`,
 `https://user:secret@new.manager.trackunit.com/assets/${id}`,
 `https://new.manager.trackunit.com:444/assets/${id}`,
 `https://new.manager.trackunit.com/assets/${id}extra`,
 'https://new.manager.trackunit.com/administration?assetId='+id,
 'https://new.manager.trackunit.com/assets','not-a-url'])assert.equal(trackunitAssetId(url),null,url);
});
