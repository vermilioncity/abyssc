ProBoards doesn't seem to have an API to dump posts.

So, the hard way it is.  This scrapes the Abyssal Chronicles forum for posts by one or more users.  Necessary prerequisites are an account on the forum, as well as a browser driver to run Selenium.

A known limitation is that some posts are duplicated, since you can only search by day and not by timestamp.  Suppose a query returns 1000 posts, and only some of January 1's were captured in them before the post limit was hit.   Requerying again for January 1 onward would mean that some of those posts would be rescraped, as well as posts missed in the first iteration.