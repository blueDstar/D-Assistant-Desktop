import {useEffect,useState} from 'react'
import {api} from './api'
export default function TrainingReadiness({projectId}:{projectId:string}){
 const [data,setData]=useState<any>(null),[error,setError]=useState('')
 const load=()=>api('/training/readiness?project_id='+encodeURIComponent(projectId)).then(setData).catch(e=>setError(e.message))
 useEffect(()=>{load()},[projectId])
 return <details className="panel"><summary>Điều kiện huấn luyện trọng số</summary>{data&&<><p>Đã huấn luyện trọng số: {data.weight_training_performed?'Có':'Chưa'}. Các model đang dùng là model huấn luyện sẵn.</p>{data.blockers.map((b:string)=><p key={b}>• {b}</p>)}<p>Dataset được duyệt: {JSON.stringify(data.approved_split_counts)}</p><p>{data.next_step}</p></>}<button onClick={load}>Kiểm tra dữ liệu lại</button>{error&&<p>{error}</p>}</details>
}
