// 모든 뉴스 뷰어 JavaScript
class NewsViewer {
    constructor() {
        this.currentPage = 1;
        this.pageSize = 50;
        this.currentSource = 'all';
        this.currentSearch = '';
        this.newsSources = {
            'all': '📰 모든 기사',
            'rss_igaming_business': '🎮 iGaming Business',
            'rss_fintech_uae': '💰 Fintech UAE',
            'rss_intergame_news': '🎲 InterGame News',
            'rss_intergame_crypto': '₿ InterGame Crypto',
            'rss_intergame_all': '🎰 InterGame All',
            'rss_intergame_abbrev': '📰 InterGame Abbrev',
            'rss_finextra_headlines': '📈 FinExtra Headlines',
            'rss_finextra_payments': '💳 FinExtra Payments',
            'rss_finextra_crypto': '🔗 FinExtra Crypto',
            'rss_player_pragmatic': '👤 Player Feed'
        };
    }

    async init() {
        await this.createUI();
        await this.loadNews();
    }

    async createUI() {
        const container = document.createElement('div');
        container.innerHTML = `
            <div style="margin: 20px 0; background: rgba(0,0,0,0.1); padding: 20px; border-radius: 10px;">
                <h2 style="margin: 0 0 15px 0; color: #60a5fa;">📰 모든 뉴스 기사</h2>
                
                <div style="margin-bottom: 15px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                    <input type="text" id="news-search-input" placeholder="기사 검색..." 
                           style="flex: 1; padding: 8px 12px; border: 1px solid rgba(255,255,255,0.2); 
                                  background: rgba(255,255,255,0.05); color: white; border-radius: 6px;">
                    <button onclick="window.newsViewer.search()" 
                            style="padding: 8px 16px; background: #60a5fa; border: none; 
                                   color: white; border-radius: 6px; cursor: pointer;">검색</button>
                </div>
                
                <div style="margin-bottom: 15px; display: flex; gap: 8px; flex-wrap: wrap;">
                    ${Object.entries(this.newsSources).map(([key, label]) => `
                        <button onclick="window.newsViewer.filter('${key}')" 
                                style="padding: 6px 12px; background: ${key === 'all' ? '#60a5fa' : 'rgba(255,255,255,0.05)'}; 
                                       border: 1px solid rgba(255,255,255,0.2); color: white; 
                                       border-radius: 6px; cursor: pointer; font-size: 12px;">
                            ${label}
                        </button>
                    `).join('')}
                </div>
                
                <div id="news-stats" style="margin-bottom: 15px; font-size: 14px; color: #9ca3af;">
                    로딩 중...
                </div>
                
                <div id="news-loader" style="text-align: center; padding: 20px;">
                    <div style="display: inline-block; width: 20px; height: 20px; 
                                border: 2px solid rgba(96, 165, 250, 0.3); 
                                border-top-color: #60a5fa; border-radius: 50%; 
                                animation: spin 1s linear infinite;"></div>
                </div>
                
                <div id="news-container" style="min-height: 300px;">
                    <!-- 뉴스 기사가 여기에 표시됩니다 -->
                </div>
                
                <div id="news-pagination" style="margin-top: 20px; text-align: center;">
                    <!-- 페이지네이션이 여기에 표시됩니다 -->
                </div>
            </div>
            <style>
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
            </style>
        `;
        
        // 대시보드에 추가
        const heroSection = document.querySelector('.hero');
        if (heroSection) {
            heroSection.parentNode.insertBefore(container, heroSection.nextSibling);
        } else {
            document.body.appendChild(container);
        }
        
        window.newsViewer = this;
    }

    async loadNews(page = 1, source = this.currentSource, search = this.currentSearch) {
        try {
            this.currentPage = page;
            this.currentSource = source;
            this.currentSearch = search;
            
            const loader = document.getElementById('news-loader');
            const container = document.getElementById('news-container');
            const stats = document.getElementById('news-stats');
            
            loader.style.display = 'block';
            container.innerHTML = '';
            
            let url = `/api/all-news?limit=${this.pageSize}&offset=${(page-1)*this.pageSize}`;
            if (source !== 'all') url += `&source=${encodeURIComponent(source)}`;
            if (search) url += `&q=${encodeURIComponent(search)}`;
            
            const response = await fetch(url);
            const data = await response.json();
            
            // 통계 표시
            const totalArticles = data.total;
            const sourceStats = Object.entries(data.source_stats || {})
                .map(([k, v]) => `${k}: ${v}`)
                .join(', ');
            stats.innerHTML = `<strong>${totalArticles}개 기사</strong> (${sourceStats})`;
            
            // 기사 목록 표시
            if (data.articles.length === 0) {
                container.innerHTML = '<div style="text-align: center; padding: 40px; color: #666;">검색 결과가 없습니다.</div>';
                loader.style.display = 'none';
                return;
            }
            
            let newsHtml = '';
            data.articles.forEach((article, idx) => {
                const articleNum = (page-1) * this.pageSize + idx + 1;
                newsHtml += `
                    <div style="margin-bottom: 16px; padding: 16px; 
                                background: rgba(255,255,255,0.03); 
                                border: 1px solid rgba(255,255,255,0.1); 
                                border-radius: 8px; transition: background 0.2s;" 
                         onmouseover="this.style.background='rgba(255,255,255,0.06)'" 
                         onmouseout="this.style.background='rgba(255,255,255,0.03)'">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                            <span style="font-size: 12px; color: #60a5fa; font-weight: 500;">
                                ${article.source_label}
                            </span>
                            <span style="font-size: 11px; color: #9ca3af;">
                                ${article.date}
                            </span>
                        </div>
                        <a href="${this.escapeHtml(article.url, true)}" 
                           target="_blank" 
                           style="color: #fff; text-decoration: none; font-weight: 500; 
                                  font-size: 14px; line-height: 1.4; display: block;">
                            ${this.escapeHtml(article.title)}
                        </a>
                        ${article.summary ? `
                            <div style="margin-top: 8px; font-size: 12px; 
                                        color: #9ca3af; line-height: 1.4;">
                                ${this.escapeHtml(article.summary.substring(0, 150))}...
                            </div>
                        ` : ''}
                    </div>
                `;
            });
            
            container.innerHTML = newsHtml;
            this.updatePagination(totalArticles, page);
            
        } catch (err) {
            console.error('뉴스 로딩 실패:', err);
            document.getElementById('news-container').innerHTML = 
                '<div style="text-align: center; padding: 40px; color: #ef4444;">뉴스를 불러오는 중 오류가 발생했습니다.</div>';
        } finally {
            document.getElementById('news-loader').style.display = 'none';
        }
    }

    updatePagination(total, currentPage) {
        const totalPages = Math.ceil(total / this.pageSize);
        const pagination = document.getElementById('news-pagination');
        
        if (totalPages <= 1) {
            pagination.innerHTML = '';
            return;
        }
        
        let paginationHtml = '<div style="display: flex; gap: 8px; align-items: center; justify-content: center;">';
        
        if (currentPage > 1) {
            paginationHtml += `
                <button onclick="window.newsViewer.loadNews(${currentPage-1})" 
                        style="padding: 6px 12px; background: rgba(96, 165, 250, 0.2); 
                               border: none; border-radius: 4px; color: #60a5fa; 
                               cursor: pointer;">
                    이전
                </button>
            `;
        }
        
        const startPage = Math.max(1, currentPage - 2);
        const endPage = Math.min(totalPages, currentPage + 2);
        
        for (let i = startPage; i <= endPage; i++) {
            if (i === currentPage) {
                paginationHtml += `
                    <button style="padding: 6px 12px; background: #60a5fa; 
                                   border: none; border-radius: 4px; color: white; 
                                   cursor: pointer; font-weight: bold;">
                        ${i}
                    </button>
                `;
            } else {
                paginationHtml += `
                    <button onclick="window.newsViewer.loadNews(${i})" 
                            style="padding: 6px 12px; background: rgba(255,255,255,0.05); 
                                   border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; 
                                   color: #fff; cursor: pointer;">
                        ${i}
                    </button>
                `;
            }
        }
        
        if (currentPage < totalPages) {
            paginationHtml += `
                <button onclick="window.newsViewer.loadNews(${currentPage+1})" 
                        style="padding: 6px 12px; background: rgba(96, 165, 250, 0.2); 
                               border: none; border-radius: 4px; color: #60a5fa; 
                               cursor: pointer;">
                    다음
                </button>
            `;
        }
        
        paginationHtml += '</div>';
        pagination.innerHTML = paginationHtml;
    }

    search() {
        const searchInput = document.getElementById('news-search-input');
        this.currentSearch = searchInput.value;
        this.loadNews(1);
    }

    filter(source) {
        this.loadNews(1, source);
    }

    escapeHtml(text, isUrl = false) {
        if (isUrl) {
            return text.replace(/"/g, '&quot;').replace(/'/g, '&#039;');
        }
        const map = {
            '&': '&amp;', '<': '&lt;', '>': '&gt;',
            '"': '&quot;', "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, m => map[m]);
    }
}

// 페이지 로드 시 뉴스 뷰어 초기화
document.addEventListener('DOMContentLoaded', () => {
    const viewer = new NewsViewer();
    viewer.init();
});