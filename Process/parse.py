from html.parser import HTMLParser
import os
from pathlib import Path
import shutil
import time
import datetime

class ArticleBounds(object):
    def __init__(self):
        self.start = None
        self.end = None
        
    def is_open(self):
        return self.start is not None and self.end is None
        
bounds = ArticleBounds()

class Parser(HTMLParser):
    def start(self):
        self.bounds = dict()
        self.bounds["article"] = ArticleBounds()
        self.bounds["h1"] = ArticleBounds()
        self.title = None
    
    def handle_starttag(self, tag, attrs):
        if tag in self.bounds:
            #print("Encountered a start tag:", tag)
            #print("Tag at {}".format(self.getpos()))
            self.bounds[tag].start, _ = self.getpos()

    def handle_endtag(self, tag):
        if tag in self.bounds:
            #print("Encountered an end tag :", tag)
            #print("Tag at {}".format(self.getpos()))
            self.bounds[tag].end, _ = self.getpos()
        
    def handle_data(self, data):
        if self.bounds["h1"].is_open():
            self.title = data
        #print("Data is {}".format(data))

def get_article_body(filename):
    f = open(filename)
    lines = f.readlines()
    
    parser = Parser()
    parser.start()
    
    for l in lines:
        parser.feed(l)
        
    bounds = parser.bounds["article"]
    
    return parser.title, "\n".join(lines[bounds.start-1:bounds.end+1])

class ArticleEntry(object):
    def __init__(self, location, title, body, subject, modified, *tags, summary = None):
        self.location = location # File location
        self.title = title # Title of article
        self.body = body # Body of article
        self.subject = subject # General subject
        self.tags = tags
        self.summary = summary
        self.modified = modified
        
    def fix_img_source(self):
        self.body.replace('file')
        
    def date_display(self, format = "%B %Y"):
        return datetime.datetime.fromtimestamp(self.modified).strftime(format)
        
    def write_to(self, dest_folder, template):
        dest = os.path.abspath(os.path.join(dest_folder, self.location))
        
        parent = os.path.split(dest)[0]
        
        os.makedirs(parent, exist_ok = True)
        
        print("Writing article {} to {}".format(self.title, dest))
        
        #print("Article {}".format(template.format(title = self.title, article = self.body)))
        
        
        
        with open(dest, 'x') as f:
            f.write(template.format(
                            title = self.title, 
                            article = self.body,
                            date = self.date_display()))
        

class SiteBuilder(object):
    def __init__(self, root = "../Export", processed = "../Processed"):
        self.root = root
        self.processed = processed
        
        self.entries = list()
    
    def get_info(self, filename):
        title, article = get_article_body(filename)
        print("Article title {}".format(title))
        parent = os.path.abspath(os.path.join(filename, ".."))
        print("Parent {}".format(os.path.split(parent)[-1]))
        subject = os.path.split(parent)[-1]
        fn = os.path.split(filename)[-1]
        
        modified = os.path.getmtime(filename)
        
        self.entries.append(
            ArticleEntry(os.path.join(subject, fn),
                        title,
                        article,
                        subject,
                        modified)
        )
    
    def _get_articles(self):
        for path, subdirs, files in os.walk(self.root):
            for name in files:
                print(os.path.join(path, name))
                
                if name.endswith(".html"):
                    print("Loading ")
                    yield os.path.join(path, name)
                    
    def load_articles(self):
        for a in self._get_articles():
            self.get_info(a)
            
        self.entries.sort(reverse = True, key = lambda e: e.modified)
            
    def build_nav(self):
        mhtml = ""
        subject = "\t<h3>{}</h3>\n"
        entry = '\t\t<p class="entry"><a href="{link}">{title}</a> {date}</p>\n'
        
        subjects = list(set([e.subject for e in self.entries]))
        
        
        for s in subjects:
            mhtml += "<div class='subject' id='{}'>\n".format(s)
            entries = [e for e in self.entries if e.subject == s]
            mhtml += subject.format(s)
            for e in entries:
                mhtml += entry.format(title = e.title, link = e.location, date = e.date_display())
            mhtml += "</div>\n"
            
        return mhtml
        
    def gen_top(self):
        f = open("base_nav.html")
        s = "\n".join(f.readlines())
        return s.format(nav = self.build_nav())
        
    def gen_site(self):
        out = os.path.abspath(self.processed)
        
        try:
            shutil.rmtree(out)
        except Exception as e:
            print("Cannot clean output dir {}".format(e))
        
        os.makedirs(out, exist_ok = True)
        
        with open(os.path.join(out, "index.html"), 'w') as f:
            f.write(self.gen_top())
        
        template = "\n".join(open("base_article.html").readlines())
        
        print(template)
        
        for e in self.entries:
            e.write_to(out, template)
        
        styles = ("md_style.css", "article_style.css","style.css")
        
        for s in styles:
            shutil.copyfile(s, os.path.join(out, s))
            
        os.makedirs(os.path.join(out, "img"), mode = 0o777, exist_ok = True)
        
        shutil.copyfile("img/background.jpg", os.path.join(out, "img", "background.jpg"))
        
if __name__ == "__main__":
    sb = SiteBuilder()
    
    sb.load_articles()
    sb.gen_site()