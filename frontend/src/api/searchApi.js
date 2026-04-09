export async function searchDockets(query, docket_type = '', agency = [], cfr_part = [], page = 1, yearFrom = '', yearTo = '') {

	// URLSearchParams make valid params that allow for spaces, special chars, etc
	const params = new URLSearchParams()
	params.append("str", query)
	params.append("page", page)

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
		throw new Error(`Search request failed: ${response.status}`)
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
