+++
title = "Using SQLite for choosing a phone to buy"
date = 2022-01-09
+++

I'd like to buy a phone that's supported by LineageOS, was preferably released recently, and has a small screen. (Am I the only one who hates big screen phones?)
I could manually browse the [LineageOS supported devices](https://wiki.lineageos.org/devices/), but it would take long to find what I'm looking for within hundreds of devices.
Luckily, the wiki of LineageOS is also open-source, so we can fetch the data and use SQLite to browse the devices.

We're going to
- fetch the data from GitHub,
- import it into SQLite with some bash magic, and
- query it with SQL.

For this I'm using Manjaro Linux (which is based on Arch Linux), but probably any UNIX-based system will work similarly.

# Fetch the data

We can find the repository by searching in [LineageOS repos on GitHub](https://github.com/LineageOS) for "wiki".
Then we can clone the repository:

```sh
mkdir find_me_a_phone
cd find_me_a_phone
git clone --depth 1 https://github.com/LineageOS/lineage_wiki.git
```

We use `--depth 1` to avoid downloading the huge history. We're only interested in the current state now.

We find that the data is in `_data/devices` folder in separate YAML files for each device:

```sh
ls lineage_wiki/_data/devices/ | head
```
gives
```
a3xelte.yml
a5xelte.yml
a5y17lte.yml
A6020.yml
a7xelte.yml
a7y17lte.yml
addison.yml
ahannah.yml
akari.yml
akatsuki.yml
```

# Import into SQLite

We can use the [yaml-to-sqlite](https://github.com/simonw/yaml-to-sqlite) tool. (Not surprisingly it's made by Simon Willison who is a master of [git scraping](https://simonwillison.net/2020/Oct/9/git-scraping/).) We can install it in Python virtualenv, not to interfere with the system Python installation.
```sh
python -m venv venv
source ./venv/bin/activate
pip install yaml-to-sqlite
```

The `yaml-to-sqlite` command will expect us to give a single big YAML file, so we will need to make a YAML list with some bash magic and load it into a single `devices.yaml` file:
```sh
for file in $(ls lineage_wiki/_data/devices/); do
    echo -n "-" >> devices.yaml
    cat lineage_wiki/_data/devices/${file} | sed -e 's/^/  /' | tail -c +2 >> devices.yaml
done;
```
Here we're
- adding a `-` to the beginning of all files,
- adding spaces to the beginning of lines (with `sed`),
- removing a space at the beginning of all files (with `tail`, to align spaces), and
- appending them to `devices.yaml`.

We get a YAML list that will look something like this:

```
- architecture: arm64
  battery: {removable: True, capacity: 2750, tech: 'Li-Ion'}
  bluetooth: {spec: '4.1', profiles: [A2DP]}
  ...
- architecture: arm64
  battery: {removable: False, capacity: 3000, tech: 'Li-Ion'}
  before_install: needs_specific_android_fw
  ...
```

We can then turn our YAML into a single SQLite table.
```sh
yaml-to-sqlite db.sqlite devices devices.yaml
```

# Query to find devices

We can use the `sqlite3` command to have a SQL shell:
```sh
sqlite3 db.sqlite
```

Browsing the columns
```
pragma table_info(devices);
```
we can find the interesting ones: `screen`, `release`, `name`.

```sql
SELECT screen, name, release FROM devices LIMIT 3;
```
gives something like this:
```
{"size": "119 mm (4.7 in)", "density": 312, "resolution": "1280x720", "technology": "Super AMOLED"}|Galaxy A3 (2016)|2015-12
{"size": "130 mm (5.2 in)", "density": 424, "resolution": "1920x1080", "technology": "Super AMOLED"}|Galaxy A5 (2016)|2015-12
{"size": "132 mm (5.2 in)", "density": 424, "resolution": "1920x1080", "technology": "Super AMOLED"}|Galaxy A5 (2017)|2017-01-02
```
We have all the info that we need, but unfortunately `size` is wrapped in JSON.
SQLite can parse JSON too:
```sql
CREATE VIEW parsed AS SELECT
    CASE WHEN json_valid(screen) = 1
    THEN json_extract(screen, "$.size")
    ELSE NULL
    END AS screen_size,
    name,
    release
FROM devices;
```

The screen size in some devices is not correct JSON, so let's just ignore those, by setting it `NULL`.
We can see that it's only 20 devices out of 373 devices (`SELECT COUNT(*) FROM parsed WHERE screen_size IS NULL OR screen_size = '';`).

We `CREATE VIEW` to make it easier to further explore the data.

This `parsed` view will have data like this:
```
119 mm (4.7 in)|Galaxy A3 (2016)|2015-12
130 mm (5.2 in)|Galaxy A5 (2016)|2015-12
132 mm (5.2 in)|Galaxy A5 (2017)|2017-01-02
```

Pretty good, but we'd like to sort on screen size in inches.
Let's parse the screen size as `NUMERIC`:

```sql
CREATE VIEW with_size AS SELECT
    CAST(substr(screen_size, instr(screen_size, '(') + 1, instr(screen_size, ' in)')) AS NUMERIC) AS size_in,
    *
FROM parsed
WHERE screen_size IS NOT NULL AND screen_size != '';
```
Here the tricky part is splitting the string.
Because SQLite does not support splitting on a character (or regex), we need to find the first occurence of a string with `instr` and use `substr` to take the values between them.
In this case we'd like `5.2` from `132 mm (5.2 in)`, so we'd like the substring between `(` and ` in)`.

Then, we can already get our answer:
```sql
SELECT size_in, name, release
FROM with_size
WHERE release >= 2018
ORDER BY size_in ASC, release DESC
LIMIT 10;
```

And we already have the candidates we can consider buying:
```
5|Aquaris E5 4G / Aquaris E5s|[{"E5 4G": 2014}, {"E5s": 2015}]
5|Xperia XZ2 Compact|2018-04
5.1|Galaxy S5 LTE Duos (G900FD/MD)|[{"SM-G900FD": "2014-06"}, {"SM-G900MD": "2014-07"}]
5.1|Galaxy S5 LTE Duos (G9006W/8W)|[{"SM-G9006W": "2014-04"}, {"SM-G9008W": "2014-06"}, {"SM-G9009W": "2014-04"}]
5.1|Galaxy S5 LTE (G9006V/8V)|[{"SM-G9006V": "2014-04"}, {"SM-G9008V": "2014-05"}]
5.2|R5/R5s (International)|[{"R8106": "2014-12"}, {"R8106s": "2015-08"}]
5.2|Moto G6 Plus|2018-05
5.2|Xperia XA2|2018-02
5.46|6.1 (2018)|2018
5.5|Le Pro3 / Le Pro3 Elite|[{"Le Pro3": "2016-10"}, {"Le Pro3 Elite": "2017-03"}]
```

Some of this is still unparsed data (where `release` is JSON and not just a date), but we already have some good candidates to look into: *Xperia XZ2 Compact*, *Moto G6 Plus*, *Xperia XA2*.

# Conclusion

Some bash magic and SQLite could make it easy to browse open data that does not have a good search interface.
It took me around 1 hour to get to this, including learning how to skip characters in bash, how parse JSON and split strings in SQLite.
