# Builds a country x firm x half-year panel of government requests for user data
# from the firms' own transparency reports (Google, Apple, Microsoft).
#
# Output: data/processed/transparency_country_firm.csv
#   firm, country, iso2, period ("2019 H1"), year, half,
#   requests, accounts, disclosed (requests where some data was disclosed; NA if not reported)
#
# Definitions (each firm counts differently -- compare within firm, not raw across firms):
#   Google    : sum of all legal-process types except Preservation Requests
#   Apple     : account + emergency requests (data about a person's account). Device and
#               financial-identifier requests are excluded: they are mostly stolen-device and
#               card-fraud lookups, not requests for a user's data.
#   Microsoft : criminal law-enforcement requests + emergency requests (civil requests excluded);
#               2013-2016 files have one combined sheet; 2015 H2 file has fractional counts (rounded)
# Run from scripts/transparency:  Rscript 03_build_transparency_panel.R

suppressMessages({library(data.table); library(readxl)})
raw <- "../../data/raw"
num <- function(x) suppressWarnings(as.numeric(gsub("[^0-9.]", "", as.character(x))))

# ---- Google ---------------------------------------------------------------
g <- fread(file.path(raw, "google-global-user-data-requests.csv"))
setnames(g, c("period_end","country","iso2","process","requests","pct","accounts"))
g <- g[process != "Preservation Requests"]
g[, `:=`(year = as.integer(substr(period_end, 1, 4)),
         half = ifelse(substr(period_end, 6, 7) == "06", "H1", "H2"))]
g[, disclosed_n := requests * pct / 100]
google <- g[, .(requests = sum(requests, na.rm = TRUE),
                accounts = sum(accounts, na.rm = TRUE),
                disclosed = sum(disclosed_n, na.rm = TRUE)),
            by = .(country, iso2, year, half)][, firm := "Google"]

# name -> ISO2 lookup, seeded from Google's CLDR codes
lookup <- unique(g[, .(country, iso2)])
extra <- c("United States of America" = "US", "United States" = "US", "USA" = "US",
           "China mainland" = "CN", "China" = "CN", "Hong Kong" = "HK", "Hong Kong SAR" = "HK",
           "Korea" = "KR", "Korea, Republic of" = "KR", "Republic of Korea" = "KR", "South Korea" = "KR",
           "Taiwan" = "TW", "Taiwan, Province of China" = "TW", "Russia" = "RU",
           "Russian Federation" = "RU", "Czech Republic" = "CZ", "Czechia" = "CZ",
           "Türkiye" = "TR", "Turkey" = "TR", "Turkiye" = "TR", "Vietnam" = "VN", "Viet Nam" = "VN",
           "UK" = "GB", "United Kingdom" = "GB", "Macau" = "MO", "Macao" = "MO",
           "Bosnia & Herzegovina" = "BA", "Bosnia and Herzegovina" = "BA",
           "Trinidad & Tobago" = "TT", "Trinidad and Tobago" = "TT",
           "Côte d'Ivoire" = "CI", "Cote d'Ivoire" = "CI", "Ivory Coast" = "CI",
           "North Macedonia" = "MK", "Macedonia" = "MK", "Moldova" = "MD", "Moldova, Republic of" = "MD",
           "Brunei" = "BN", "Brunei Darussalam" = "BN", "Laos" = "LA", "Palestine" = "PS",
           "Kosovo" = "XK", "Curacao" = "CW", "Curaçao" = "CW", "St. Lucia" = "LC", "Saint Lucia" = "LC",
           "Bahamas" = "BS", "The Bahamas" = "BS", "Iran" = "IR", "Venezuela" = "VE",
           "Bolivia" = "BO", "Tanzania" = "TZ", "Congo - Kinshasa" = "CD", "Congo - Brazzaville" = "CG",
           "Myanmar (Burma)" = "MM", "Myanmar" = "MM", "Holy See" = "VA", "Vatican City" = "VA",
           "Eswatini" = "SZ", "Swaziland" = "SZ", "Cabo Verde" = "CV", "Cape Verde" = "CV",
           "Faroe Islands" = "FO", "Guernsey" = "GG", "Jersey" = "JE", "Isle of Man" = "IM",
           "Gibraltar" = "GI", "Puerto Rico" = "PR", "Reunion" = "RE", "Réunion" = "RE",
           # names missing from Google's list, plus Microsoft's spellings/typos
           "Mozambique" = "MZ", "Turks and Caicos Islands" = "TC", "Morocco" = "MA",
           "Nicaragua" = "NI", "Barbados" = "BB", "British Virgin Islands" = "VG",
           "French Polynesia" = "PF", "Sierra Leone" = "SL", "Venezuala" = "VE",
           "Bosnia And Herzegovina" = "BA", "Cote D'Ivoire" = "CI", "Korea, Republic Of" = "KR",
           "Urugay" = "UY", "Beligum" = "BE", "Swizerland" = "CH", "Kosovo (Republic of)" = "XK",
           "UAE" = "AE", "Moldova (Republic of)" = "MD", "Serbia (incl Kosovo)" = "RS",
           "Serbia (incl kosovo)" = "RS", "Cypress" = "CY", "Kingdom of Bahrain" = "BH")
           # dropped on purpose: "French Southern Territories", "To Be Determined"
to_iso <- function(x) {
  x <- trimws(gsub("\\s+|\\*", " ", x))
  out <- lookup$iso2[match(tolower(x), tolower(lookup$country))]
  out[is.na(out)] <- extra[x[is.na(out)]]
  out
}

# ---- Apple ----------------------------------------------------------------
ap_files <- c(account = "account_requests.csv", emergency = "emergency_requests.csv")
apple <- rbindlist(lapply(names(ap_files), function(k) {
  x <- fread(file.path(raw, "transparency/apple", ap_files[[k]]), colClasses = "character")
  setnames(x, 1, "period"); setnames(x, 4, "country")
  rq <- grep("Requests Received$", names(x), value = TRUE)[1]
  ac <- grep("Specified in", names(x), value = TRUE)[1]
  dp <- grep("^Requests where (Data Provided|Only Non-Content|Content Provided)", names(x), value = TRUE)
  data.table(period = x$period, country = x$country, type = k,
             requests = num(x[[rq]]),
             accounts = if (is.na(ac)) NA_real_ else num(x[[ac]]),
             disclosed = if (length(dp)) rowSums(sapply(dp, function(d) num(x[[d]])), na.rm = TRUE) else NA_real_)
}))
apple[, `:=`(year = as.integer(substr(period, 1, 4)), half = substr(period, 6, 7))]
apple <- apple[, .(requests = sum(requests, na.rm = TRUE), accounts = sum(accounts, na.rm = TRUE),
                   disclosed = sum(disclosed, na.rm = TRUE)), by = .(country, year, half)]
apple[, `:=`(iso2 = to_iso(country), firm = "Apple")]

# ---- Microsoft ------------------------------------------------------------
read_ms_sheet <- function(f, sheet) {
  x <- as.data.frame(read_excel(f, sheet = sheet, col_names = FALSE, .name_repair = "minimal"))
  start <- which(toupper(trimws(x[[1]])) == "TOTAL")[1]
  if (is.na(start)) return(NULL)
  hdr <- apply(x[seq_len(start - 1), , drop = FALSE], 2, function(c) paste(na.omit(c), collapse = " "))
  # the "#" count column sits immediately right of each "%" column
  ci <- which(grepl("Disclosure of Content", hdr))[1] + 1
  ni <- which(grepl("Non-Content", hdr))[1] + 1
  body <- x[(start + 1):nrow(x), , drop = FALSE]
  body <- body[!is.na(body[[1]]) & nzchar(trimws(body[[1]])), , drop = FALSE]
  body <- body[!grepl("^(\\*|Note|Source|Total)", body[[1]], ignore.case = TRUE), , drop = FALSE]
  vals <- lapply(body[-1], num)
  numcols <- which(sapply(vals, function(v) sum(!is.na(v)) > 0)) + 1
  # columns: total requests, accounts, then pairs (% , #) for content / non-content / ...
  data.table(country = trimws(body[[1]]),
             requests = num(body[[numcols[1]]]),
             accounts = num(body[[numcols[2]]]),
             content_n = if (is.na(ci)) NA_real_ else num(body[[ci]]),
             noncontent_n = if (is.na(ni)) NA_real_ else num(body[[ni]]))
}
ms_files <- list.files(file.path(raw, "transparency/microsoft"), "^LERR-\\d{4}-H[12]\\.xlsx$", full.names = TRUE)
microsoft <- rbindlist(lapply(ms_files, function(f) {
  sh <- excel_sheets(f)
  # law-enforcement sheets only: drop civil requests and stray scratch sheets;
  # 2013 H1 splits Microsoft / Skype into two sheets, which are summed
  use <- sh[!grepl("Civil", sh)]
  if (length(use) > 1) use <- use[use != "Sheet1"]
  d <- rbindlist(lapply(use, function(s) read_ms_sheet(f, s)), fill = TRUE)
  m <- regmatches(basename(f), regexec("(\\d{4})-(H[12])", basename(f)))[[1]]
  d[, `:=`(year = as.integer(m[2]), half = m[3])]
}), fill = TRUE)
microsoft <- microsoft[!is.na(requests),
                       .(requests = round(sum(requests)), accounts = sum(accounts, na.rm = TRUE),
                         disclosed = round(sum(content_n, noncontent_n, na.rm = TRUE))),
                       by = .(country, year, half)]
microsoft[, `:=`(iso2 = to_iso(country), firm = "Microsoft")]

# ---- Combine --------------------------------------------------------------
panel <- rbindlist(list(google, apple, microsoft), use.names = TRUE, fill = TRUE)
panel <- panel[requests > 0 & !is.na(iso2) & iso2 != ""]
unmatched <- unique(rbind(apple[is.na(iso2), .(firm, country)], microsoft[is.na(iso2), .(firm, country)]))
if (nrow(unmatched)) { message("Unmatched country names (dropped):"); print(unmatched) }
# one canonical country name per ISO2 (Google's spelling)
canon <- lookup[, .(country_std = country[1]), by = iso2]
panel <- merge(panel, canon, by = "iso2", all.x = TRUE)
panel[is.na(country_std), country_std := country]
panel <- panel[, .(requests = sum(requests), accounts = sum(accounts, na.rm = TRUE),
                   disclosed = sum(disclosed, na.rm = TRUE)),
               by = .(firm, country = country_std, iso2, year, half)]
panel[, period := paste(year, half)]
setorder(panel, firm, year, half, -requests)
dir.create("../../data/processed", showWarnings = FALSE)
fwrite(panel, "../../data/processed/transparency_country_firm.csv")
print(panel[, .(rows = .N, countries = uniqueN(iso2), first = min(period), last = max(period),
                requests = sum(requests)), by = firm])
