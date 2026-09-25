"""Read the same-VIN XGSS catalog using its authenticated, read-only data API.

Contracts observed in the deployed XGSS client: app.56976b91.js (2026-09-25).
No browser cookies, browser storage, arbitrary URLs or write APIs are used.
Authentication URLs and tokens live only in this request's memory.
"""
import heapq
import json
import re
import time
from urllib.parse import parse_qs, urlsplit

import httpx
from app import xgss_handoff as handoff
from app import xgss_catalog_images as catalog_images
from app import xgss_research_images as images
from app.xgss_catalog_context import CatalogRow

BASE = 'https://xgss.xcmg.com'
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_SVG_BYTES = catalog_images.MAX_SVG_BYTES
MAX_REQUESTS = 48
MAX_TREE_READS = 20
MAX_NODES = 2000


class DirectReadError(RuntimeError):
    def __init__(self, kind, message, retryable=True, *, preserve_completed=False):
        super().__init__(message)
        self.kind, self.message, self.retryable = kind, message, retryable
        # Only a transport failure can leave earlier, fully checked categories
        # useful. Identity, schema, permissions and cancellation stay fail-closed.
        self.preserve_completed = preserve_completed


def fail(message='XGSS 数据格式发生变化，未保存本次资料。'):
    raise DirectReadError('direct_schema', message)


def identifier(value):
    if isinstance(value, bool) or not re.fullmatch(r'[1-9][0-9]{0,14}', str(value)):
        fail()
    return str(value)


def label(value, limit=160):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c)<32 for c in value):
        fail()
    return value.strip()


def normalized(value):
    return re.sub(r'\s+', '', str(value)).casefold()


def terms_checked(terms):
    if not isinstance(terms, list) or not 1 <= len(terms) <= 12:
        raise DirectReadError('direct_invalid', '请提供 1–12 个部件检索词。', False)
    result=[]
    for term in terms:
        if not isinstance(term,str) or not 2 <= len(term.strip()) <= 40 or any(ord(c)<32 for c in term):
            raise DirectReadError('direct_invalid', '部件检索词格式无效。', False)
        if term.strip() not in result: result.append(term.strip())
    return result


from app.xgss_catalog_search import term_matches, route_score


def svg_png(raw):
    """Rasterize only verified standalone SVG and self-contained raster content."""
    try:
        return catalog_images.rasterize_svg(raw)
    except catalog_images.RendererUnavailable as error:
        raise DirectReadError('direct_unavailable', str(error)) from None
    except catalog_images.CatalogImageError as error:
        raise DirectReadError('direct_image', str(error), False) from None


class CatalogClient:
    def __init__(self, vin, check_cancelled, progress, *, client=None):
        self.vin=vin
        self.check_cancelled=check_cancelled
        self.progress=progress
        self.requests=0
        self.show_hidden_codes=False
        self.tree_issues=[]
        self.deadline=time.monotonic()+85
        self.client=client or httpx.Client(base_url=BASE, timeout=httpx.Timeout(15), follow_redirects=False,
                                          headers={'Accept-Language':'zh-CN','productId':'0'})

    def close(self):
        self.client.headers.pop('token',None)
        self.client.close()

    def check(self):
        self.check_cancelled()
        if time.monotonic()>self.deadline:
            raise DirectReadError('direct_timeout','XGSS 读取超时，已有资料保持不变，请重试。')

    def request(self, method, path, *, params=None, body=None, image=False):
        self.check()
        if self.requests>=MAX_REQUESTS:
            raise DirectReadError('direct_limit','本次图册查询已达到范围限制，请缩小检索词。',False)
        # Every route is built internally from a verified catalog response.
        allowed=(method=='POST' and path=='/api/thrid/crm/login/init') or (method=='GET' and (
            re.fullmatch(r'/api/rest/part/car/root/[A-Z0-9]{8,32}',path) or
            re.fullmatch(r'/api/rest/part/car/children/[1-9][0-9]*/[A-Z0-9]{8,32}',path) or
            re.fullmatch(r'/api/rest/partlist/list/[1-9][0-9]*',path) or
            re.fullmatch(r'/api/rest/partlist/view/[1-9][0-9]*/[1-9][0-9]*',path) or
            re.fullmatch(r'/api/doc/image2d/[1-9][0-9]*\.svg',path)))
        if not allowed: fail()
        self.requests+=1
        try:
            with self.client.stream(method,path,params=params,json=body) as response:
                if response.status_code in (401,403):
                    raise DirectReadError('direct_auth','XGSS 未授权本次资料读取，可尝试网页入口。')
                if image and response.status_code == 404:
                    raise DirectReadError('direct_image', '该图纸暂未在资料服务中找到。')
                if response.status_code!=200:
                    raise DirectReadError('direct_unavailable','XGSS 资料接口暂不可用，可使用网页读取。',
                                          preserve_completed=500<=response.status_code<600)
                limit=MAX_SVG_BYTES if image else MAX_JSON_BYTES
                chunks=[];length=0
                for chunk in response.iter_bytes():
                    self.check();length+=len(chunk)
                    if length>limit: raise DirectReadError('direct_limit','XGSS 单次响应超过读取范围。',False)
                    chunks.append(chunk)
                raw=b''.join(chunks)
            self.check()
            if image: return raw
            payload=json.loads(raw)
        except httpx.TimeoutException:
            raise DirectReadError('direct_timeout','XGSS 读取超时，已有资料保持不变，请重试。',
                                  preserve_completed=True) from None
        except httpx.HTTPError:
            raise DirectReadError('direct_unavailable','XGSS 网络或响应异常，可使用网页读取。',
                                  preserve_completed=True) from None
        except ValueError:
            # Invalid JSON is a schema failure, not a transient transport error.
            raise DirectReadError('direct_schema','XGSS 返回资料格式无法核对，未保存本次资料。') from None
        if not isinstance(payload,dict) or payload.get('success') is not True or 'data' not in payload:
            raise DirectReadError('direct_schema','XGSS 未返回有效资料，未保存本次读取。')
        return payload['data']

    def authenticate(self):
        self.progress('正在连接 XGSS 图册接口…');self.check()
        try: entry=handoff.request_page(self.vin)
        except (handoff.XGSSUnavailable,handoff.XGSSUpstreamError):
            raise DirectReadError('direct_auth','XGSS 认证入口暂不可用，可尝试网页读取。') from None
        self.check()
        if not handoff.valid_destination(entry.get('url')): fail()
        url=urlsplit(entry['url'])
        if url.fragment.partition('?')[0]!='/CrmJump': fail('XGSS 认证入口格式已改变，可使用网页读取。')
        fields=parse_qs(url.fragment.partition('?')[2],keep_blank_values=True)
        if fields.get('vin') != [self.vin]:
            raise DirectReadError('direct_identity','XGSS 认证返回的 VIN 不一致，已停止读取。',False)
        if any(len(fields.get(k,[]))!=1 or not fields[k][0] or len(fields[k][0])>4096 for k in ('token','random','userId')): fail()
        session=self.request('POST','/api/thrid/crm/login/init',body={k:fields[k][0] for k in ('token','random','userId')})
        if not isinstance(session,dict) or not isinstance(session.get('token'),str) or not session['token'] or len(session['token'])>16384: fail()
        self.client.headers['token']=session['token']
        self.client.headers['productId']='1000' if session.get('productDomains') else '0'
        user_type=session.get('userType') or {}
        self.show_hidden_codes=isinstance(user_type,dict) and str(user_type.get('code')) in ('-1','0')

    def roots(self):
        data=self.request('GET','/api/rest/part/car/root/'+self.vin)
        if not isinstance(data,dict) or data.get('pin')!=self.vin:
            raise DirectReadError('direct_identity','图册资料与当前 VIN 不一致，已停止读取。',False)
        roots=data.get('partRoots')
        if not isinstance(roots,list) or len(roots)>30: fail()
        permission=data.get('vinPermision')
        if not isinstance(permission,dict) or permission.get('PER_PART_ATLAS_VIEW')!='valid':
            raise DirectReadError('direct_auth','当前 XGSS 身份未获准查看该设备图册。')
        if any(not isinstance(r,dict) for r in roots): fail()
        return [self.node(r) for r in roots if r.get('type')=='0']

    def node(self, raw):
        if not isinstance(raw,dict): fail()
        return {**raw,'id':identifier(raw.get('id')),'name':label(raw.get('name')),
                'code':label(raw.get('code'),100)}

    def children(self,node,root):
        params={'code':root['code']}
        if node['id']==root['id']: params['nodeType']='topPart'
        data=self.request('GET',f"/api/rest/part/car/children/{node['id']}/{self.vin}",params=params)
        if not isinstance(data,list) or len(data)>MAX_NODES: fail()
        result=[]
        for item in data:
            if not isinstance(item,dict): fail()
            if str(item.get('id')) in ('10038','10039','10040'):
                self.tree_issues.append('保养包与维修包需通过网页核对')
                continue
            result.append(self.node(item))
        return result

    def pages(self,node,root,path,remaining):
        listings=self.request('GET','/api/rest/partlist/list/'+node['id'],params={'code':root['code']})
        if not isinstance(listings,list) or len(listings)>30: fail()
        result=[];issues=[]
        for raw in listings:
            if self.requests>MAX_REQUESTS-2:
                issues.append(node['name']+'：已达到本次查询范围');break
            if len(result)>=remaining:
                issues.append(node['name']+'：还有其他图册页');break
            listing=self.node(raw)
            if listing['code'].removeprefix('PL_')!=node['code']: fail('图册明细与分类编码不一致，已停止读取。')
            detail=self.request('GET',f"/api/rest/partlist/view/{listing['id']}/{root['id']}",params={'car':self.vin})
            if not isinstance(detail,dict) or identifier(detail.get('id'))!=listing['id'] or detail.get('code')!=listing['code']:
                fail('图册明细与所选分类不一致，已停止读取。')
            if not isinstance(detail.get('parts'),list): fail()
            rows=[]
            for part in detail['parts']:
                if not isinstance(part,dict): fail()
                # Match the official UI's material-code visibility for this role.
                if str(part.get('purchaseStatus'))=='2' and not part.get('topPart') and not self.show_hidden_codes:
                    issues.append(node['name']+'：部分料号未开放');continue
                if not part.get('code') or not part.get('name'): continue
                try:
                    rows.append(CatalogRow(name=part['name'],part_number=part['code'],
                                           figure_ref=str(part['ballNum']) if part.get('ballNum') is not None else None,
                                           quantity=str(part['amount']) if part.get('amount') is not None else None).model_dump())
                except ValueError:
                    issues.append(node['name']+'：部分条目字段无法识别');continue
            if len(rows)>200: raise DirectReadError('direct_limit','所选分类超过 200 条零件，请缩小检索范围。',False)
            if not rows: continue
            title=label(detail.get('name'),200)
            page={'source':'xgss_api_catalog','source_url':BASE+'/', 'vin':self.vin,'title':title,
                  'assembly_path':path,'items':rows,'manual_sections':[],
                  'coverage':'api_selected_categories','illustrations':[]}
            docs=detail.get('d2ids') or []
            if not isinstance(docs,list) or len(docs)>30: fail()
            if docs:
                sheets = []
                if len(docs) > catalog_images.MAX_DRAWING_SHEETS:
                    issues.append(title + '：其余图纸尚未读取')
                for index, document in enumerate(docs[:catalog_images.MAX_DRAWING_SHEETS], 1):
                    if not isinstance(document, str) or not re.fullmatch(r'[1-9][0-9]*\.svg', document):
                        issues.append(title + f'：第 {index} 张图纸格式暂不支持')
                        continue
                    self.progress('正在读取 ' + title + f' 的图纸 {index}/{len(docs)}…')
                    for attempt in range(2):
                        if self.requests >= MAX_REQUESTS:
                            issues.append(title + f'：第 {index} 张图纸尚未读取')
                            break
                        try:
                            png = svg_png(self.request('GET', '/api/doc/image2d/' + document, image=True))
                            sheets.append((index, document, png))
                            break
                        except DirectReadError as exc:
                            # Do not lose verified part rows because one drawing is
                            # missing/temporarily unavailable. Auth, redirects, source
                            # identity, and cancellation are still fatal.
                            recoverable = exc.kind == 'direct_image' or exc.preserve_completed
                            if not recoverable:
                                raise
                            self.check()
                            if exc.preserve_completed and attempt == 0:
                                continue
                            issues.append(title + f'：第 {index} 张图纸暂未取得，零件资料已保留')
                            break
                if sheets:
                    try:
                        page['illustrations'] = [catalog_images.sheet_illustration(sheets, title=title, total=len(docs))]
                    except (catalog_images.CatalogImageError, images.ImageCaptureError):
                        issues.append(title + '：分类图纸合成未完成，零件资料已保留')
            else:
                issues.append(title + '：分类未提供图纸')
            result.append(page)
        return result,list(dict.fromkeys(issues))


def collect_catalog(vin, terms, *, check_cancelled=lambda:None, progress=lambda _:None,
                    max_pages=6, max_parts=400):
    if not isinstance(vin,str) or not re.fullmatch(r'[A-Z0-9]{8,32}',vin):
        raise DirectReadError('direct_identity','请核对当前设备 VIN。',False)
    terms=terms_checked(terms)
    if not 1<=max_pages<=8 or not 1<=max_parts<=400:
        raise DirectReadError('evidence_limit','当前资料容量已满，请新建排查后读取。',False)
    client=CatalogClient(vin,check_cancelled,progress)
    try:
        client.authenticate()
        roots=client.roots()
        queue=[];seq=0;seen=set();pages=[];matched=set();unresolved=[];tree_reads=0;nodes=0
        def retain_completed(error,node):
            if not pages or not error.preserve_completed:
                raise error
            # In particular, never turn the outer cancellation/deadline into a
            # successful partial result after a slow upstream request.
            check_cancelled()
            unresolved.append(node['name']+'：后续读取暂未完成，已保留此前核对的分类')
        def enqueue(node,root,path):
            nonlocal seq,nodes
            nodes+=1
            if nodes>MAX_NODES: raise DirectReadError('direct_limit','图册目录超出读取范围，请缩小检索范围。',False)
            seq+=1
            direct_score=sum(1 for term in terms if term_matches(node['name']+' '+node['code'],term))
            route=route_score(node['name'],terms)
            score=(100+direct_score if direct_score else 20*route)
            # Traverse identity/wrapper nodes first; inspect matching branches next.
            wrapper=node['id']==root['id'] or node.get('topPart') is True
            heapq.heappush(queue,(-1000 if wrapper else -score,seq,node,root,path,wrapper,score,direct_score,route))
        for root in roots: enqueue(root,root,[root['name']])
        while queue and len(pages)<max_pages:
            client.check()
            # Reserve enough requests for a complete category and its illustration;
            # save an explicit partial result instead of exhausting midway through it.
            if client.requests>=MAX_REQUESTS-4:
                unresolved.append('已达到本次查询范围，其他分类尚未读取');break
            _,_,node,root,path,wrapper,score,direct_score,route=heapq.heappop(queue)
            key=(root['id'],node['id'])
            if key in seen: continue
            if pages and not wrapper and score<=0:
                # Terms include synonyms and optional parts, so not every term
                # has its own category. Do not scan the rest of the whole BOM
                # merely to exhaust unmatched terms after useful evidence exists.
                unresolved.append('未继续遍历无匹配的整机分类；未命中检索词仍待核对')
                break
            seen.add(key)
            if not wrapper and (direct_score or route==2):
                progress('正在查询 '+node['name']+'…')
                try:
                    found,issues=client.pages(node,root,path,max_pages-len(pages))
                except DirectReadError as error:
                    retain_completed(error,node);break
                if sum(len(p['items']) for p in pages+found)>max_parts:
                    unresolved.append(node['name']+'：超出本次零件范围');break
                pages.extend(found);unresolved.extend(issues)
                if found:
                    labels=[node['name']+' '+node['code']]
                    labels.extend(row['name']+' '+row['part_number'] for page in found for row in page['items'])
                    matched.update(t for t in terms if any(term_matches(value,t) for value in labels))
                    if len(matched)==len(terms):
                        # The requested categories are covered. Do not walk the
                        # rest of the whole-machine BOM after satisfying them.
                        queue.clear();break
            if node.get('leaf') is not True and len(path)<10 and tree_reads<MAX_TREE_READS and len(pages)<max_pages and client.requests<MAX_REQUESTS:
                # Explore wrappers and matched branches first. A small bounded scan
                # also finds deeply nested harness/control categories when needed.
                tree_reads+=1
                try:
                    children=client.children(node,root)
                except DirectReadError as error:
                    retain_completed(error,node);break
                for child in children: enqueue(child,root,[*path,child['name']])
        unresolved.extend(client.tree_issues)
        if queue: unresolved.append('其余分类未纳入本次读取范围')
        unmatched=[term for term in terms if term not in matched]
        if not pages: raise DirectReadError('direct_no_match','尚未在该设备图册中找到匹配分类，可使用网页继续查找。')
        status='partial' if unmatched or unresolved else 'completed'
        return {'pages':pages,'status':status,'matched_terms':[t for t in terms if t in matched],
                'unmatched_terms':unmatched,'unresolved':list(dict.fromkeys(unresolved))[:24],
                'requests':client.requests,'source':'xgss_api_catalog','tree_reads':tree_reads,
                'message':f'已通过 XGSS 接口读取 {len(pages)} 页资料。'}
    finally:
        client.close()
