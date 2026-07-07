# React / TSX 學習筆記

> 以 DocuMind 的 App.tsx 為範例，假設你熟悉 Python，第一次接觸 React。

---

## TSX 是什麼

TSX = TypeScript + JSX（在 JavaScript 裡直接寫 HTML）。

```tsx
// 這是合法的 TSX：函式裡面直接 return HTML
const App = () => {
  return <div>Hello</div>;
};
```

Python 類比：就像在 Python 裡用字串拼 HTML，但 TSX 是真的 HTML 語法，有型別檢查。

---

## 檔案結構總覽

App.tsx 從上到下分三區：

```
1. import 區       → 引入外部套件和 icon
2. interface 區    → 定義資料型別（TypeScript 專屬）
3. App 函式        → 主體，分兩部分：
   ├── 上半部：狀態（state）和函式（邏輯）
   └── return：UI 長什麼樣（HTML）
```

---

## Interface（型別定義）

TypeScript 可以定義「這個物件裡面有哪些欄位」：

```typescript
interface Message {
  role: 'user' | 'ai';  // 只能是這兩個字串之一
  content: string;
}
```

Python 類比：
```python
from typing import Literal
from dataclasses import dataclass

@dataclass
class Message:
    role: Literal['user', 'ai']
    content: str
```

---

## useState — 狀態管理

React 的核心概念：**畫面跟著資料變**。

你不能直接改一個變數然後期待畫面更新，要用 `useState` 宣告「這個變數改變時，重新渲染畫面」。

```typescript
const [question, setQuestion] = useState<string>('');
//     ↑ 讀取     ↑ 修改函式              ↑ 預設值
```

Python 類比：
```python
# Python 的 class attribute 類似，但 React 會自動追蹤變化
class App:
    question: str = ''
    
    def set_question(self, value):
        self.question = value
        self.re_render()  # React 自動幫你做這件事
```

**App.tsx 裡用到的所有 state：**

| State | 型別 | 用途 |
|-------|------|------|
| `question` | `string` | 輸入框的文字 |
| `chatHistory` | `Message[]` | 所有對話紀錄 |
| `loading` | `boolean` | AI 思考中的 loading 狀態 |
| `selectedFiles` | `FileList \| null` | 使用者選擇但還沒上傳的檔案 |
| `modelProvider` | `string` | 目前選擇的模型（openai/ollama）|
| `isUploading` | `boolean` | 上傳中的 loading 狀態 |
| `uploadedFiles` | `string[]` | 知識庫裡的檔名清單 |

---

## useEffect — 在特定時機執行程式

```typescript
useEffect(() => {
  // 這裡的程式碼在「頁面載入」時執行一次
}, []);  // [] = 空陣列，代表只在載入時執行一次
```

App.tsx 用它在頁面載入時撈檔案清單：

```typescript
useEffect(() => {
  axios.get('http://127.0.0.1:8000/api/document/list').then((res) => {
    setUploadedFiles(res.data.filenames);
  });
}, []);
```

Python 類比：
```python
# 像是 __init__ 裡面的初始化
def __init__(self):
    response = requests.get('.../api/document/list')
    self.uploaded_files = response.json()['filenames']
```

---

## axios — 打 API

axios 是 JavaScript 版的 `requests`。

```typescript
// GET
axios.get('網址').then((res) => {
  console.log(res.data)  // 回傳的 JSON
});

// POST
axios.post('網址', {
  question: "你好",
  model_provider: "openai"
});
```

Python 對照：
```python
# GET
res = requests.get('網址')
print(res.json())

# POST
requests.post('網址', json={
    "question": "你好",
    "model_provider": "openai"
})
```

---

## return 裡的 HTML（JSX）

### 大括號 `{}` = 插入 Python 變數

```tsx
<p>{question}</p>       // 顯示 question 變數的值
<p>{1 + 1}</p>          // 顯示 2
```

Python 類比：f-string 的 `{}`

### 條件渲染

```tsx
{loading && <div>思考中...</div>}
// 相當於：if loading: render div
```

```tsx
{chatHistory.length === 0 && <div>還沒有對話</div>}
```

### 列表渲染

```tsx
{uploadedFiles.map((name, i) => (
  <li key={i}>{name}</li>
))}
```

Python 類比：
```python
[f"<li>{name}</li>" for i, name in enumerate(uploaded_files)]
```

`key={i}` 是 React 要求的，讓它知道哪個元素是哪個，用 index 當 key。

---

## 事件處理

```tsx
<input
  value={question}
  onChange={(e) => setQuestion(e.target.value)}
  // e = 事件物件，e.target.value = 輸入框的當前值
/>

<button onClick={handleSend}>送出</button>
```

Python 類比：callback function / event listener。

---

## Model 切換下拉選單（本次實作）

```tsx
<select
  value={modelProvider}                              // 顯示目前的值
  onChange={(e) => setModelProvider(e.target.value)} // 選到新值時更新 state
>
  <option value="openai">OpenAI GPT-4o</option>
  <option value="ollama">Ollama（本地）</option>
</select>
```

POST 時把 state 的值帶進去：

```typescript
axios.post('...api/chat/ask', {
  question: question,
  model_provider: modelProvider  // 直接用 state 變數
});
```

---

## 知識庫檔案清單（本次實作）

頁面載入時打 API，把結果存進 state，再用 `.map()` 渲染：

```typescript
// 1. state
const [uploadedFiles, setUploadedFiles] = useState<string[]>([]);

// 2. 頁面載入時撈資料
useEffect(() => {
  axios.get('.../api/document/list').then((res) => {
    setUploadedFiles(res.data.filenames);
  });
}, []);
```

```tsx
{/* 3. UI */}
{uploadedFiles.map((name, i) => (
  <li key={i}>
    <FileText size={12} />
    <span>{name}</span>
  </li>
))}
```

---

## className = CSS class

React 用 `className` 而不是 `class`（因為 `class` 是 JavaScript 的保留字）。

樣式用 Tailwind CSS，直接在 className 裡寫 utility class：

```tsx
<div className="flex h-screen bg-slate-50">
//              ↑ flex  ↑ 全高  ↑ 背景色
```
