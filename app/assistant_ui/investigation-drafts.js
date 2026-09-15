class InvestigationDrafts {
  constructor(){this.currentKey=null;this.drafts=new Map();}
  switchTo(key,current){
    if(key!==null && key===this.currentKey)return {...current};
    if(this.currentKey!==null)this.drafts.set(this.currentKey,{...current});
    this.currentKey=key;
    const empty={question:'',observations:'',task:current.task,language:current.language,priorRecordId:null};
    return key!==null && this.drafts.has(key)?{...this.drafts.get(key)}:empty;
  }
}
if(typeof module!=='undefined')module.exports={InvestigationDrafts};
