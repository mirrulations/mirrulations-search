/** Backend GET /search/?sort_by= — relevance when omitted; else document_count | comment_count | modify_date */
const SORT_BY_VALUES = new Set(['document_count', 'comment_count', 'modify_date'])

export async function searchDockets(query, docket_type = '', agency = [], cfr_part = [], page = 1, yearFrom = '', yearTo = '', sortBy = '') {

	// URLSearchParams make valid params that allow for spaces, special chars, etc
	const params = new URLSearchParams()
	params.append("str", query)
	params.append("page", page)
	const key = (sortBy || '').trim()
	if (key && SORT_BY_VALUES.has(key)) {
		params.append("sort_by", key)
	}

	const normalizeDate = (val, isEnd = false) => {
		if (/^\d{4}$/.test((val || '').trim())) {
		  return isEnd ? `${val.trim()}-12-31` : `${val.trim()}-01-01`;
		}
		return val;
	  };
	
	  const startDate = normalizeDate(yearFrom, false);
	  const endDate   = normalizeDate(yearTo,   true);

	agency.forEach(a => params.append("agency", a))

	// Append CFR parts
  	// Each CFR part becomes something like: title:part
  	cfr_part.forEach(({ title, part }) => {
    	params.append("cfr_part", `${title}:${part}`)
  	})

	if (docket_type) {
		params.append("docket_type", docket_type)
	}

	if (startDate) {
		params.append("start_date", startDate);
	}
	
	if (endDate) {
		params.append("end_date", endDate);
	}

	const response = await fetch(
        `/search/?${params.toString()}`
    )

	if (response.status === 401) {
		throw new Error("UNAUTHORIZED")
	}
	if (!response.ok) {
		let message = "Search failed";
		try {
			const err = await response.json();
			if (err.error) {
				message = err.error;
			}
		} catch (e) {
			// ignore JSON parse errors
		}
		throw new Error(message);
	}

	const results = await response.json()

	const pagination = {
		page: Number(response.headers.get("X-Page")),
		pageSize: Number(response.headers.get("X-Page-Size")),
		totalResults: Number(response.headers.get("X-Total-Results")),
		totalPages: Number(response.headers.get("X-Total-Pages")),
		hasNext: response.headers.get("X-Has-Next") === "true",
		hasPrev: response.headers.get("X-Has-Prev") === "true",
	  }

	return { results, pagination }
}

export async function getAuthStatus() {
	const response = await fetch("/auth/status")
	if (!response.ok) {
		return { logged_in: false }
	}
	return response.json()
}
