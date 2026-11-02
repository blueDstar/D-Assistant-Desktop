"""Local starter projects, explicitly labelled templates, not LLM output."""
import json
from pathlib import Path
import re
from typing import Literal

from pydantic import Field

from .coding import router,workspace,BatchInput,WriteInput,propose
from .schemas import StrictModel


class ProjectInput(StrictModel):
    name:str=Field(min_length=1,max_length=48,pattern=r'^[a-z][a-z0-9-]*$')
    template:Literal['python-cli','static-web','react-ts','fastapi']


@router.get('/templates')
def templates():
    return [{'id':'python-cli','name':'Python CLI','description':'Project Python chạy bằng python -m, README và pyproject.toml.'},{'id':'static-web','name':'Web HTML/CSS/JS','description':'Website tĩnh không cần tải dependency.'},{'id':'react-ts','name':'React + TypeScript','description':'Vite/React; npm install và chạy là thao tác bạn chọn sau.'},{'id':'fastapi','name':'FastAPI','description':'API Python nhỏ có health endpoint và hướng dẫn môi trường ảo.'}]


def template_files(name,kind):
    module=name.replace('-','_')
    readme=f'# {name}\n\nProject được khởi tạo từ mẫu D-bot `{kind}`.\n\n## Phát triển\n\n'
    if kind=='python-cli':
        return {'README.md':readme+f'Python >=3.12. Không cần dependency để chạy mẫu.\n\n```powershell\npython -m {module} --name Dat\n```\n',
                'pyproject.toml':f'[project]\nname = "{name}"\nversion = "0.1.0"\nrequires-python = ">=3.12"\n',
                f'{module}/__init__.py':'',
                f'{module}/__main__.py':'import argparse\n\ndef main():\n    parser = argparse.ArgumentParser(description="A small Python CLI")\n    parser.add_argument("--name", default="world")\n    args = parser.parse_args()\n    print(f"Hello, {args.name}!")\n\nif __name__ == "__main__":\n    main()\n',
                '.gitignore':'__pycache__/\n.venv/\n*.pyc\n.env\n'}
    if kind=='static-web':
        return {'README.md':readme+'Mở index.html, hoặc chạy `python -m http.server 8080` rồi mở http://127.0.0.1:8080.\n',
                'index.html':f'<!doctype html>\n<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{name}</title><link rel="stylesheet" href="style.css"></head><body><main><p>D-BOT / STARTER</p><h1>{name}</h1><p id="message">Project đã sẵn sàng để phát triển.</p><button id="action">Thử tương tác</button></main><script src="app.js"></script></body></html>\n',
                'style.css':'*{box-sizing:border-box}body{margin:0;background:#121212;color:#eee;font:16px/1.6 system-ui}main{max-width:800px;margin:15vh auto;padding:24px}h1{font-size:clamp(36px,8vw,72px)}button{padding:12px 20px;background:#eee;color:#121212;border:0;border-radius:4px;cursor:pointer}\n',
                'app.js':"document.querySelector('#action').addEventListener('click', () => { document.querySelector('#message').textContent = 'JavaScript đang hoạt động.'; });\n"}
    if kind=='react-ts':
        package={'name':name,'version':'0.1.0','private':True,'type':'module','scripts':{'dev':'vite --host 127.0.0.1','build':'tsc --noEmit && vite build'},'dependencies':{'react':'19.1.0','react-dom':'19.1.0'},'devDependencies':{'typescript':'5.9.3','vite':'7.3.7','@vitejs/plugin-react':'5.0.4','@types/react':'19.1.0','@types/react-dom':'19.1.0'}}
        return {'README.md':readme+'Cần Node >=20.19 hoặc >=22.12.\n\n```powershell\nnpm install\nnpm run dev\nnpm run build\n```\n\nD-bot chưa chạy lệnh cài đặt hoặc server cho project này.\n',
                'package.json':json.dumps(package,indent=2)+'\n',
                'index.html':f'<!doctype html>\n<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{name}</title></head><body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body></html>\n',
                'tsconfig.json':json.dumps({'compilerOptions':{'target':'ES2022','module':'ESNext','moduleResolution':'Bundler','jsx':'react-jsx','strict':True,'skipLibCheck':True,'noEmit':True,'lib':['ES2022','DOM','DOM.Iterable']},'include':['src']},indent=2)+'\n',
                'vite.config.ts':"import { defineConfig } from 'vite'\nimport react from '@vitejs/plugin-react'\nexport default defineConfig({plugins:[react()]})\n",
                'src/main.tsx':f"import {{ useState }} from 'react'\nimport {{ createRoot }} from 'react-dom/client'\nimport './style.css'\nfunction App() {{ const [count,setCount]=useState(0); return <main><p>D-BOT / STARTER</p><h1>{name}</h1><button onClick={{()=>setCount(c=>c+1)}}>Số lần nhấn: {{count}}</button></main> }}\ncreateRoot(document.getElementById('root')!).render(<App />)\n",
                'src/style.css':'body{margin:0;background:#151515;color:#eee;font:16px/1.6 system-ui}main{max-width:800px;margin:15vh auto;padding:24px}button{padding:12px 20px;cursor:pointer}\n',
                '.gitignore':'node_modules/\ndist/\n.env\n'}
    return {'README.md':readme+'Python >=3.12.\n\n```powershell\npython -m venv .venv\n.venv\\Scripts\\python -m pip install -e .\n.venv\\Scripts\\python -m uvicorn app.main:app --host 127.0.0.1 --port 8080\n```\n\nGET http://127.0.0.1:8080/health. Cài đặt/chạy server là thao tác bạn chọn.\n',
            'pyproject.toml':f'[build-system]\nrequires = ["setuptools>=68"]\nbuild-backend = "setuptools.build_meta"\n\n[project]\nname = "{name}"\nversion = "0.1.0"\nrequires-python = ">=3.12"\ndependencies = ["fastapi>=0.115,<1", "uvicorn>=0.30,<1"]\n',
            'app/__init__.py':'','app/main.py':'from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get("/health")\ndef health():\n    return {"ok": True}\n',
            '.gitignore':'.venv/\n__pycache__/\n.env\n'}


@router.post('/workspaces/{id}/projects')
def create_project(id:str,body:ProjectInput):
    ws=workspace(id)
    if (Path(ws['root'])/body.name).exists():raise ValueError('Thư mục project đã tồn tại; chọn tên mới để tránh ghi đè')
    files=[WriteInput(path=body.name+'/'+path,content=text) for path,text in template_files(body.name,body.template).items()]
    return propose(ws,BatchInput(summary=f'Khởi tạo {body.name} từ mẫu {body.template}',files=files),'template')
