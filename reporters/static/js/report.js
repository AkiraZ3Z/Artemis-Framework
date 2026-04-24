// Artemis Framework 测试报告交互脚本
(function() {
    'use strict';
    
    // 报告管理器
    class ReportManager {
        constructor() {
            this.testcases = [];
            this.currentFilter = 'all';
            this.currentSearch = '';
            this.filters = {};
            
            this.initialize();
        }
        
        initialize() {
            this.collectTestcases();
            this.setupEventListeners();
            this.setupFilters();
            this.applyFilters();
            
            // 自动展开失败的测试用例
            setTimeout(() => this.expandFailedTestcases(), 100);
        }
        
        collectTestcases() {
            const testcaseElements = document.querySelectorAll('.testcase-card');
            this.testcases = Array.from(testcaseElements).map(element => ({
                element: element,
                id: element.dataset.id,
                name: element.querySelector('.testcase-title')?.textContent || '',
                module: element.dataset.module || '',
                status: element.dataset.status || '',
                priority: element.dataset.priority || 'medium',
                visible: true
            }));
        }
        
        setupEventListeners() {
            // 筛选按钮
            document.querySelectorAll('.filter-btn').forEach(button => {
                button.addEventListener('click', (e) => {
                    this.handleFilterClick(e);
                });
            });
            
            // 搜索输入
            const searchInput = document.getElementById('searchInput');
            if (searchInput) {
                searchInput.addEventListener('input', this.debounce((e) => {
                    this.handleSearchInput(e);
                }, 300));
                
                // 搜索按钮
                const searchBtn = document.getElementById('searchBtn');
                if (searchBtn) {
                    searchBtn.addEventListener('click', () => {
                        this.handleSearchInput({ target: searchInput });
                    });
                }
            }
        }
        
        setupFilters() {
            // 收集所有可能的筛选条件
            this.filters = {
                status: new Set(),
                module: new Set(),
                priority: new Set()
            };
            
            this.testcases.forEach(testcase => {
                this.filters.status.add(testcase.status);
                this.filters.module.add(testcase.module);
                this.filters.priority.add(testcase.priority);
            });
        }
        
        handleFilterClick(event) {
            const button = event.currentTarget;
            const filter = button.dataset.filter;
            
            if (filter === this.currentFilter) return;
            
            // 更新活动按钮
            document.querySelectorAll('.filter-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            button.classList.add('active');
            
            this.currentFilter = filter;
            this.applyFilters();
            
            // 滚动到测试用例列表
            this.scrollToTestcases();
        }
        
        handleSearchInput(event) {
            this.currentSearch = event.target.value.trim().toLowerCase();
            this.applyFilters();
        }
        
        applyFilters() {
            let visibleCount = 0;
            
            this.testcases.forEach(testcase => {
                const matchesFilter = this.matchesFilter(testcase);
                const matchesSearch = this.matchesSearch(testcase);
                
                testcase.visible = matchesFilter && matchesSearch;
                testcase.element.style.display = testcase.visible ? 'block' : 'none';
                
                if (testcase.visible) {
                    visibleCount++;
                }
            });
            
            this.updateCounter(visibleCount);
        }
        
        matchesFilter(testcase) {
            if (this.currentFilter === 'all') return true;
            return testcase.status === this.currentFilter;
        }
        
        matchesSearch(testcase) {
            if (!this.currentSearch) return true;
            
            const searchTerm = this.currentSearch.toLowerCase();
            return (
                testcase.id.toLowerCase().includes(searchTerm) ||
                testcase.name.toLowerCase().includes(searchTerm) ||
                testcase.module.toLowerCase().includes(searchTerm)
            );
        }
        
        updateCounter(visibleCount) {
            const filterButtons = document.querySelectorAll('.filter-btn');
            filterButtons.forEach(button => {
                const filter = button.dataset.filter;
                if (filter === 'all') {
                    button.textContent = `全部 (${visibleCount})`;
                }
            });
        }
        
        expandFailedTestcases() {
            this.testcases.forEach(testcase => {
                if (testcase.status === 'fail' || testcase.status === 'error') {
                    const testcaseId = testcase.element.dataset.id;
                    window.toggleTestcaseDetails(testcaseId);
                }
            });
        }
        
        scrollToTestcases() {
            const testcasesSection = document.querySelector('.testcases-section');
            if (testcasesSection) {
                testcasesSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        }
        
        debounce(func, wait) {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        }
    }
    
    // 初始化报告管理器
    document.addEventListener('DOMContentLoaded', () => {
        window.reportManager = new ReportManager();
    });
    
})();

// 工具函数
function initSearch() {
    const searchInput = document.getElementById('searchInput');
    const searchBtn = document.getElementById('searchBtn');
    
    if (!searchInput || !searchBtn) return;
    
    const performSearch = () => {
        const searchTerm = searchInput.value.trim().toLowerCase();
        if (!searchTerm) {
            // 重置所有显示
            document.querySelectorAll('.testcase-card').forEach(card => {
                card.style.display = 'block';
            });
            return;
        }
        
        document.querySelectorAll('.testcase-card').forEach(card => {
            const id = card.dataset.id.toLowerCase();
            const name = card.querySelector('.testcase-title')?.textContent.toLowerCase() || '';
            const module = card.dataset.module?.toLowerCase() || '';
            
            if (id.includes(searchTerm) || name.includes(searchTerm) || module.includes(searchTerm)) {
                card.style.display = 'block';
            } else {
                card.style.display = 'none';
            }
        });
    };
    
    searchInput.addEventListener('input', debounce(performSearch, 300));
    searchBtn.addEventListener('click', performSearch);
}

function initFilters() {
    document.querySelectorAll('.filter-btn').forEach(button => {
        button.addEventListener('click', function() {
            // 移除所有按钮的active类
            document.querySelectorAll('.filter-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            
            // 为当前按钮添加active类
            this.classList.add('active');
            
            const filter = this.dataset.filter;
            filterTestcases(filter);
        });
    });
}

function filterTestcases(filter) {
    const testcases = document.querySelectorAll('.testcase-card');
    
    testcases.forEach(testcase => {
        if (filter === 'all') {
            testcase.style.display = 'block';
        } else {
            const status = testcase.dataset.status;
            if (status === filter) {
                testcase.style.display = 'block';
            } else {
                testcase.style.display = 'none';
            }
        }
    });
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}