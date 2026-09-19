# pip install passlib[bcrypt]
# pip install python-jose[cryptography]
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, INTEGER, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.tools import tool
from langchain.agents import create_agent
import os
# 🟩 ADDED
from passlib.context import CryptContext
# 🟩 ADDED
from jose import jwt


load_dotenv()

# 🟩 ADDED
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not set")

if not ALGORITHM:
    raise RuntimeError("ALGORITHM is not set")
    
# 🟩 ADDED
def hash_password(password: str):
    return pwd_context.hash(password)


# 🟩 ADDED
def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)

# 🟩 ADDED
def create_access_token(username: str, role: str):

    payload = {
        "username": username,
        "role": role
    }

    token = jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return token

# 🟩 ADDED
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import HTTPException

security = HTTPBearer()


# 🟩 ADDED
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        username = payload.get("username")
        role = payload.get("role")

        if username is None or role is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid token"
            )

        return {
            "username": username,
            "role": role,
            "token": token
        }   
    except Exception as e:
        print("JWT ERROR:", e)
        raise HTTPException(
            status_code=401,
            detail=str(e)
        )
    
def require_admin(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )

    return current_user

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(DATABASE_URL)
base = declarative_base()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class product(base):
    __tablename__ = "Products"

    id = Column(INTEGER, primary_key=True)
    name = Column(String(50))
    price = Column(INTEGER)
    stock = Column(INTEGER)

class order(base):
    __tablename__ = "orders"

    id = Column(INTEGER, primary_key=True, autoincrement=True)
    product_id = Column(INTEGER, nullable=False)
    quantity = Column(INTEGER, nullable=False)
    customer_name = Column(String(100), nullable=False)
    customer_email = Column(String(150), nullable=False)
    total_price = Column(INTEGER, nullable=False)
    status = Column(String(30), nullable=False, default="Pending")
    order_date = Column(DateTime, nullable=False)
    address = Column(String(255), nullable=False)

# 🟩 ADDED
class user(base):
    __tablename__ = "users"

    id = Column(INTEGER, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="customer")

base.metadata.create_all(engine)

class productdata(BaseModel):
    name: str
    price: int
    stock: int

class patchdata(BaseModel): #patch
    name: str | None = None
    price: int | None = None
    stock: int | None = None

class UserCreate(BaseModel):
    username: str
    password: str

# 🟩 ADDED
class LoginRequest(BaseModel):
    username: str
    password: str

# 🟩 ADDED
@app.post("/register")
def register(data: UserCreate, db: Session = Depends(get_db)):

    existing_user = db.query(user).filter(
        user.username == data.username
    ).first()

    if existing_user:
        return {"msg": "username already exists"}

    hashed_password = hash_password(data.password)

    new_user = user(
        username=data.username,
        password=hashed_password,
        role="customer"
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "msg": "user registered",
        "username": new_user.username,
        "role": new_user.role
    }

# 🟩 ADDED
@app.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):

    existing_user = db.query(user).filter(
        user.username == data.username
    ).first()

    if not existing_user:
        return {"msg": "invalid username or password"}

    if not verify_password(data.password, existing_user.password):
        return {"msg": "invalid username or password"}

    # 🟨 CHANG ED
    access_token = create_access_token(
        existing_user.username,
        existing_user.role
    )

    return {
    "msg": "login successful",
    "access_token": access_token,
    "token_type": "bearer",
    "username": existing_user.username,
    "role": existing_user.role
}
    

@app.get("/")
def products(db: Session = Depends(get_db)):
    return db.query(product).all()
    
# 🟨 CHANGED
@app.get("/order")
def orders(
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    return db.query(order).all()


# 🟨 CHANGED
@app.post("/insert")
def insert(
    data: productdata,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    s = product(
        name=data.name,
        price=data.price,
        stock=data.stock
    )

    db.add(s)
    db.commit()

    return {"msg": "inserted"}


# 🟨 CHANGED
@app.put("/update/{id}")
def update(
    id: int,
    data: productdata,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    s = db.query(product).filter(product.id == id).first()

    if not s:
        return {"msg": "product not found"}

    s.name = data.name
    s.price = data.price
    s.stock = data.stock

    db.commit()

    return {"msg": "update"}

# 🟨 CHANGED
@app.patch("/patch/{id}")
def patch(
    id: int,
    data: patchdata,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    s = db.query(product).filter(product.id == id).first()

    if not s:
        return {"msg": "product not found"}

    if data.name is not None:
        s.name = data.name

    if data.price is not None:
        s.price = data.price

    if data.stock is not None:
        s.stock = data.stock

    db.commit()

    return {"msg": "updated"}

# 🟨 CHANGED
@app.delete("/delete/{id}")
def delete(
    id: int,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):

    s = db.query(product).filter(product.id == id).first()

    if not s:
        return {"msg": "product not found"}

    db.delete(s)
    db.commit()

    return {"msg": "deleted"}






# =========================
# LANGCHAIN + GEMINI
# =========================

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0.8
)





# =========================
# AGENT
# =========================

def get_agent(current_user, db):

    @tool
    def myproductdata():
        """give me all product data"""

        products = db.query(product).all()

        return [
            {
                "id": p.id,
                "name": p.name,
                "price": p.price,
                "stock": p.stock
            }
            for p in products
        ]

    if current_user["role"] == "admin":

        @tool
        def myordersdata():
            """give me all orders data"""

            orders = db.query(order).all()

            return [
                {
                    "id": o.id,
                    "product_id": o.product_id,
                    "quantity": o.quantity,
                    "customer_name": o.customer_name,
                    "customer_email": o.customer_email,
                    "total_price": o.total_price,
                    "status": o.status,
                    "order_date": str(o.order_date),
                    "address": o.address
                }
                for o in orders
            ]

        tools = [
            myproductdata,
            myordersdata
        ]

    else:
        tools = [
            myproductdata
        ]

    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt="""
        you are a helpful assistant.

        use the available tools whenever needed.

        do not make up information.

        use the tool data to answer.
        """
    )

    return agent

# =========================
# CHAT REQUEST
# =========================

class ChatRequest(BaseModel):

    question: str


# =========================
# CHAT API
# =========================

@app.post("/chat")
def chat(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    print("CURRENT USER:", current_user)

    agent = get_agent(current_user, db)

    result = agent.invoke({
        "messages": [
            ("user", request.question)
        ]
    })

    answer = result["messages"][-1].content

    # Gemini/LangChain content જો object/list હોય
    if isinstance(answer, list):

        text_parts = []

        for item in answer:

            if isinstance(item, dict):

                if "text" in item:
                    text_parts.append(item["text"])

            elif isinstance(item, str):

                text_parts.append(item)

        answer = "\n".join(text_parts)

    # Final safety
    if not isinstance(answer, str):
        answer = str(answer)

    return {
        "answer": answer
    }