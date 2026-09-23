// Every page's timestamps in the viewer's own time zone and locale. The server renders each
// as <time datetime="2026-09-23T15:51:09Z">2026-09-23 15:51 UTC</time> (the `timestamp`
// filter, server/views.py); this swaps the text for the local time and keeps the UTC text
// as the hover title. Without the script the UTC text stays, which is still correct.

// A block, so its names stay out of the scope the page's other plain scripts share.
{
  const format = new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });

  for (const element of document.querySelectorAll("time[datetime]")) {
    const when = new Date(element.dateTime);
    if (Number.isNaN(when.getTime())) {
      continue;
    }
    element.title = element.textContent;
    element.textContent = format.format(when);
  }
}
