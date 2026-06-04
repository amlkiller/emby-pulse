from jinja2 import Environment, FileSystemLoader
from fastapi.templating import Jinja2Templates


def create_templates(directory: str = "templates", *, autoescape: bool = True) -> Jinja2Templates:
    env = Environment(loader=FileSystemLoader(directory), autoescape=autoescape)
    return Jinja2Templates(env=env)
